#!/usr/bin/env bash
set -euo pipefail

PIDS=()
VITE_PORT="${VITE_PORT:-5173}"
API_PORT="${API_PORT:-8000}"
RERUN_GRPC_PORT="${RERUN_GRPC_PORT:-9876}"
RERUN_WEB_PORT="${RERUN_WEB_PORT:-9090}"
GUI_URL="${CAMERA_GUARD_GUI_URL:-http://localhost:${VITE_PORT}}"
DEV_SKIP_PRE_CLEANUP="${DEV_SKIP_PRE_CLEANUP:-0}"

list_listening_pids() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true
}

wait_for_port_to_clear() {
  local port="$1"
  local max_attempts=20
  local attempt=1
  while [[ $attempt -le $max_attempts ]]; do
    if ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
    attempt=$((attempt + 1))
  done
  return 1
}

kill_port_if_in_use() {
  local port="$1"
  local name="$2"
  local pids
  pids="$(list_listening_pids "${port}" | tr '\n' ' ' | sed -E 's/[[:space:]]+$//')"

  if [[ -z "${pids}" ]]; then
    return 0
  fi

  echo "==> Cleaning stale ${name} listener on port ${port} (PIDs: ${pids})"
  for pid in ${pids}; do
    kill "${pid}" >/dev/null 2>&1 || true
  done

  if wait_for_port_to_clear "${port}"; then
    return 0
  fi

  local remaining
  remaining="$(list_listening_pids "${port}" | tr '\n' ' ' | sed -E 's/[[:space:]]+$//')"
  if [[ -n "${remaining}" ]]; then
    echo "==> Escalating cleanup for ${name} on port ${port} (PIDs: ${remaining})"
    for pid in ${remaining}; do
      kill -9 "${pid}" >/dev/null 2>&1 || true
    done
  fi

  if ! wait_for_port_to_clear "${port}"; then
    echo "ERROR: ${name} port ${port} is still in use after cleanup." >&2
    exit 1
  fi
}

cleanup_preexisting_ports() {
  local cleaned_any=0

  for entry in \
    "${VITE_PORT}:Vite" \
    "${API_PORT}:FastAPI" \
    "${RERUN_GRPC_PORT}:Rerun gRPC" \
    "${RERUN_WEB_PORT}:Rerun web"
  do
    local port="${entry%%:*}"
    local name="${entry#*:}"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      cleaned_any=1
    fi
    kill_port_if_in_use "${port}" "${name}"
  done

  if [[ "${cleaned_any}" -eq 0 ]]; then
    echo "==> No stale listeners found on dev ports."
  fi
}

cleanup() {
  local exit_code=$?
  trap - EXIT SIGINT SIGTERM
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  # Ensure grandchildren (uvicorn reloader/vite worker) are also terminated.
  if [[ "${#PIDS[@]}" -gt 0 ]]; then
    kill 0 >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
  exit "$exit_code"
}

require_free_port() {
  local port="$1"
  local name="$2"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: ${name} port ${port} is already in use. Stop existing process first." >&2
    exit 1
  fi
}

cleanup_only=0
for arg in "$@"; do
  case "$arg" in
    --cleanup-only)
      cleanup_only=1
      ;;
    *)
      echo "ERROR: unknown argument '${arg}'." >&2
      echo "Usage: bash scripts/dev.sh [--cleanup-only]" >&2
      exit 2
      ;;
  esac
done

if [[ "${DEV_SKIP_PRE_CLEANUP}" != "1" ]]; then
  cleanup_preexisting_ports
fi

require_free_port "${VITE_PORT}" "Vite"
require_free_port "${API_PORT}" "FastAPI"
require_free_port "${RERUN_GRPC_PORT}" "Rerun gRPC"
require_free_port "${RERUN_WEB_PORT}" "Rerun web"

if [[ "${cleanup_only}" == "1" ]]; then
  echo "==> Dev port cleanup complete."
  exit 0
fi

trap cleanup EXIT SIGINT SIGTERM

echo "==> Starting client (Vite)..."
(cd client && npm run dev -- --host localhost --port "${VITE_PORT}" --strictPort) &
PIDS+=("$!")

echo "==> Starting server (FastAPI)..."
(cd server && uv run uvicorn main:app --reload --port "${API_PORT}") &
PIDS+=("$!")

echo "==> Starting Rerun demo (trajectory + 3D model)..."
uv run --project server python scripts/run_rerun_demo.py &
PIDS+=("$!")

if [[ "${SKIP_CAMERA_GUARD:-0}" != "1" ]]; then
  echo "==> Running camera live guard (WebRTC)..."
  CAMERA_GUARD_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
    uv run --project server python scripts/check_camera_live_webrtc.py

  echo "==> Running camera live guard (GUI + snapshot)..."
  CAMERA_GUARD_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
    CAMERA_GUARD_GUI_URL="${GUI_URL}" \
    node scripts/check_camera_live_gui.mjs
else
  echo "==> SKIP_CAMERA_GUARD=1, skipping camera live guards."
fi

wait
