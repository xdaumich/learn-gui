#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PIDS=()
MEDIAMTX_RTSP_PORT="${MEDIAMTX_RTSP_PORT:-8554}"
MEDIAMTX_WHEP_PORT="${MEDIAMTX_WHEP_PORT:-8889}"
MEDIAMTX_API_PORT="${MEDIAMTX_API_PORT:-9997}"
MEDIAMTX_CONFIG_PATH="${MEDIAMTX_CONFIG_PATH:-mediamtx.yml}"
CAMERA_WIDTH="${CAMERA_WIDTH:-640}"
CAMERA_HEIGHT="${CAMERA_HEIGHT:-480}"
CAMERA_FPS="${CAMERA_FPS:-30}"
CAMERA_STARTUP_TIMEOUT="${CAMERA_STARTUP_TIMEOUT:-20.0}"
CAMERA_RETRY_INTERVAL="${CAMERA_RETRY_INTERVAL:-0.5}"
DEV_SKIP_PRE_CLEANUP="${DEV_SKIP_PRE_CLEANUP:-0}"
MEDIAMTX_BIN="${MEDIAMTX_BIN:-$(command -v mediamtx || true)}"

if [[ -z "${MEDIAMTX_BIN}" ]]; then
  echo "ERROR: mediamtx binary not found on PATH." >&2
  echo "Install MediaMTX on Thor, then retry." >&2
  exit 1
fi

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
  pkill -f 'tc-camera|mediamtx' >/dev/null 2>&1 || true
  # mediamtx may have been started as root; escalate if needed
  if pgrep -f mediamtx >/dev/null 2>&1; then
    sudo pkill -f mediamtx >/dev/null 2>&1 || true
  fi

  for entry in \
    "${MEDIAMTX_RTSP_PORT}:MediaMTX RTSP" \
    "${MEDIAMTX_WHEP_PORT}:MediaMTX WHEP" \
    "${MEDIAMTX_API_PORT}:MediaMTX API"
  do
    local port="${entry%%:*}"
    local name="${entry#*:}"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      cleaned_any=1
    fi
    kill_port_if_in_use "${port}" "${name}"
  done

  if [[ "${cleaned_any}" -eq 0 ]]; then
    echo "==> No stale listeners found on remote media ports."
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
      echo "Usage: bash scripts/dev_remote.sh [--cleanup-only]" >&2
      exit 2
      ;;
  esac
done

if [[ "${DEV_SKIP_PRE_CLEANUP}" != "1" ]]; then
  cleanup_preexisting_ports
fi

require_free_port "${MEDIAMTX_RTSP_PORT}" "MediaMTX RTSP"
require_free_port "${MEDIAMTX_WHEP_PORT}" "MediaMTX WHEP"
require_free_port "${MEDIAMTX_API_PORT}" "MediaMTX API"

if [[ "${cleanup_only}" == "1" ]]; then
  echo "==> Remote media port cleanup complete."
  exit 0
fi

trap cleanup EXIT SIGINT SIGTERM

if [[ -f "${MEDIAMTX_CONFIG_PATH}" ]]; then
  echo "==> Starting MediaMTX with ${MEDIAMTX_CONFIG_PATH}..."
  "${MEDIAMTX_BIN}" "${MEDIAMTX_CONFIG_PATH}" &
else
  echo "==> MediaMTX config not found at ${MEDIAMTX_CONFIG_PATH}; starting defaults."
  "${MEDIAMTX_BIN}" &
fi
PIDS+=("$!")

echo "==> Starting camera relay runner on remote..."
uv run --project server tc-camera \
  --width "${CAMERA_WIDTH}" \
  --height "${CAMERA_HEIGHT}" \
  --fps "${CAMERA_FPS}" \
  --startup-timeout "${CAMERA_STARTUP_TIMEOUT}" \
  --retry-interval "${CAMERA_RETRY_INTERVAL}" &
PIDS+=("$!")

wait
