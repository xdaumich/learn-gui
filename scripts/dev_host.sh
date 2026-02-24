#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PIDS=()
HOST_VITE_PORT="${HOST_VITE_PORT:-5173}"
HOST_API_PORT="${HOST_API_PORT:-8000}"
HOST_RERUN_GRPC_PORT="${HOST_RERUN_GRPC_PORT:-9876}"
HOST_RERUN_WEB_PORT="${HOST_RERUN_WEB_PORT:-9090}"
ROBOT_STATE_PORT="${ROBOT_STATE_PORT:-5555}"
ROBOT_HEARTBEAT_PATH="${ROBOT_HEARTBEAT_PATH:-data_logs/.robot_heartbeat.json}"
RUN_ROBOT_RUNNER="${RUN_ROBOT_RUNNER:-0}"
DEV_SKIP_PRE_CLEANUP="${DEV_SKIP_PRE_CLEANUP:-0}"
VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://127.0.0.1:${HOST_API_PORT}}"
RERUN_GRPC_URL="${RERUN_GRPC_URL:-rerun+http://127.0.0.1:${HOST_RERUN_GRPC_PORT}/proxy}"
RERUN_WEB_URL="${RERUN_WEB_URL:-http://localhost:${HOST_RERUN_WEB_PORT}}"

list_listening_pids() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true
}

wait_for_port_to_clear() {
  local port="$1"
  local max_attempts=20
  local attempt=1
  while [[ ${attempt} -le ${max_attempts} ]]; do
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
  pkill -f 'tc-gui|tc-robot' >/dev/null 2>&1 || true

  for entry in \
    "${HOST_VITE_PORT}:Vite" \
    "${HOST_API_PORT}:FastAPI" \
    "${HOST_RERUN_GRPC_PORT}:Rerun gRPC" \
    "${HOST_RERUN_WEB_PORT}:Rerun web" \
    "${ROBOT_STATE_PORT}:Robot state ZMQ"
  do
    local port="${entry%%:*}"
    local name="${entry#*:}"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      cleaned_any=1
    fi
    kill_port_if_in_use "${port}" "${name}"
  done

  if [[ "${cleaned_any}" -eq 0 ]]; then
    echo "==> No stale listeners found on host dev ports."
  fi
}

cleanup() {
  local exit_code=$?
  trap - EXIT SIGINT SIGTERM
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
  done
  if [[ "${#PIDS[@]}" -gt 0 ]]; then
    kill 0 >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
  exit "${exit_code}"
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
  case "${arg}" in
    --cleanup-only)
      cleanup_only=1
      ;;
    *)
      echo "ERROR: unknown argument '${arg}'." >&2
      echo "Usage: bash scripts/dev_host.sh [--cleanup-only]" >&2
      exit 2
      ;;
  esac
done

if [[ "${DEV_SKIP_PRE_CLEANUP}" != "1" ]]; then
  cleanup_preexisting_ports
fi

require_free_port "${HOST_VITE_PORT}" "Vite"
require_free_port "${HOST_API_PORT}" "FastAPI"
require_free_port "${HOST_RERUN_GRPC_PORT}" "Rerun gRPC"
require_free_port "${HOST_RERUN_WEB_PORT}" "Rerun web"
require_free_port "${ROBOT_STATE_PORT}" "Robot state ZMQ"

if [[ "${cleanup_only}" == "1" ]]; then
  echo "==> Host dev port cleanup complete."
  exit 0
fi

trap cleanup EXIT SIGINT SIGTERM

echo "==> Host mode enabled."
echo "==> API base URL: ${VITE_API_BASE_URL}"

echo "==> Starting GUI API + Rerun viewer on host..."
uv run --project server tc-gui --no-client --port "${HOST_API_PORT}" &
PIDS+=("$!")

echo "==> Starting host frontend (Vite)..."
(
  cd client
  VITE_API_BASE_URL="${VITE_API_BASE_URL}" \
  VITE_RERUN_WEB_ORIGIN="http://localhost:${HOST_RERUN_WEB_PORT}" \
  VITE_RERUN_GRPC_ORIGIN="http://127.0.0.1:${HOST_RERUN_GRPC_PORT}" \
    npm run dev -- --host 0.0.0.0 --port "${HOST_VITE_PORT}" --strictPort
) &
PIDS+=("$!")

if [[ "${RUN_ROBOT_RUNNER}" == "1" ]]; then
  echo "==> Starting optional robot runner..."
  uv run --project server tc-robot \
    --no-open-browser \
    --rerun-grpc-url "${RERUN_GRPC_URL}" \
    --rerun-web-url "${RERUN_WEB_URL}" \
    --heartbeat-path "${ROBOT_HEARTBEAT_PATH}" &
  PIDS+=("$!")
else
  echo "==> RUN_ROBOT_RUNNER!=1, skipping robot runner."
fi

wait
