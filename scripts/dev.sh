#!/usr/bin/env bash
set -euo pipefail

PIDS=()
VITE_PORT="${VITE_PORT:-5173}"
API_PORT="${API_PORT:-8000}"
RERUN_GRPC_PORT="${RERUN_GRPC_PORT:-9876}"
RERUN_WEB_PORT="${RERUN_WEB_PORT:-9090}"
RERUN_GRPC_URL="${RERUN_GRPC_URL:-rerun+http://127.0.0.1:${RERUN_GRPC_PORT}/proxy}"
RERUN_WEB_URL="${RERUN_WEB_URL:-http://localhost:${RERUN_WEB_PORT}}"
MEDIAMTX_RTSP_PORT="${MEDIAMTX_RTSP_PORT:-8554}"
MEDIAMTX_WHEP_PORT="${MEDIAMTX_WHEP_PORT:-8889}"
MEDIAMTX_API_PORT="${MEDIAMTX_API_PORT:-9997}"
ROBOT_STATE_PORT="${ROBOT_STATE_PORT:-5555}"
RECORDER_STATUS_PORT="${RECORDER_STATUS_PORT:-5556}"
RECORDER_CONTROL_PORT="${RECORDER_CONTROL_PORT:-5557}"
ROBOT_HEARTBEAT_PATH="${ROBOT_HEARTBEAT_PATH:-data_logs/.robot_heartbeat.json}"
MEDIAMTX_CONFIG_PATH="${MEDIAMTX_CONFIG_PATH:-mediamtx.yml}"
CAMERA_WIDTH="${CAMERA_WIDTH:-640}"
CAMERA_HEIGHT="${CAMERA_HEIGHT:-480}"
CAMERA_FPS="${CAMERA_FPS:-30}"
CAMERA_STARTUP_TIMEOUT="${CAMERA_STARTUP_TIMEOUT:-0}"
CAMERA_RETRY_INTERVAL="${CAMERA_RETRY_INTERVAL:-1.0}"
GUI_URL="${CAMERA_GUARD_GUI_URL:-http://localhost:${VITE_PORT}}"
GUI_GUARD_BROWSER="${CAMERA_GUARD_GUI_BROWSER:-chromium}"
DEV_SKIP_PRE_CLEANUP="${DEV_SKIP_PRE_CLEANUP:-0}"
MEDIAMTX_BIN="$(command -v mediamtx || true)"
GUI_NO_RERUN="${GUI_NO_RERUN:-0}"

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

  # Stale split-runner processes can survive abnormal shutdowns. Best-effort stop.
  pkill -f 'tc-gui|tc-camera|tc-recorder|tc-robot|run_robot\.py' >/dev/null 2>&1 || true

  for entry in \
    "${VITE_PORT}:Vite" \
    "${API_PORT}:FastAPI" \
    "${RERUN_GRPC_PORT}:Rerun gRPC" \
    "${RERUN_WEB_PORT}:Rerun web" \
    "${ROBOT_STATE_PORT}:Robot state ZMQ" \
    "${RECORDER_STATUS_PORT}:Recorder status ZMQ" \
    "${RECORDER_CONTROL_PORT}:Recorder control ZMQ"
  do
    local port="${entry%%:*}"
    local name="${entry#*:}"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      cleaned_any=1
    fi
    kill_port_if_in_use "${port}" "${name}"
  done

  if [[ -n "${MEDIAMTX_BIN}" ]]; then
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
  fi

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
if [[ "${GUI_NO_RERUN}" != "1" ]]; then
  require_free_port "${RERUN_GRPC_PORT}" "Rerun gRPC"
  require_free_port "${RERUN_WEB_PORT}" "Rerun web"
fi
require_free_port "${ROBOT_STATE_PORT}" "Robot state ZMQ"
require_free_port "${RECORDER_STATUS_PORT}" "Recorder status ZMQ"
require_free_port "${RECORDER_CONTROL_PORT}" "Recorder control ZMQ"
if [[ -n "${MEDIAMTX_BIN}" ]]; then
  require_free_port "${MEDIAMTX_RTSP_PORT}" "MediaMTX RTSP"
  require_free_port "${MEDIAMTX_WHEP_PORT}" "MediaMTX WHEP"
  require_free_port "${MEDIAMTX_API_PORT}" "MediaMTX API"
fi

if [[ "${cleanup_only}" == "1" ]]; then
  echo "==> Dev port cleanup complete."
  exit 0
fi

trap cleanup EXIT SIGINT SIGTERM

echo "==> Starting client (Vite)..."
(cd client && npm run dev -- --host localhost --port "${VITE_PORT}" --strictPort) &
PIDS+=("$!")

echo "==> Starting GUI API + Rerun viewer..."
GUI_ARGS=(--no-client --port "${API_PORT}")
if [[ "${GUI_NO_RERUN}" == "1" ]]; then
  echo "==> GUI_NO_RERUN=1, starting GUI API without Rerun services."
  GUI_ARGS+=(--no-rerun)
fi
uv run --project server tc-gui "${GUI_ARGS[@]}" &
PIDS+=("$!")

if [[ -n "${MEDIAMTX_BIN}" ]]; then
  if [[ -f "${MEDIAMTX_CONFIG_PATH}" ]]; then
    echo "==> Starting MediaMTX relay with ${MEDIAMTX_CONFIG_PATH}..."
    "${MEDIAMTX_BIN}" "${MEDIAMTX_CONFIG_PATH}" &
  else
    echo "==> MediaMTX config not found at ${MEDIAMTX_CONFIG_PATH}; starting defaults."
    "${MEDIAMTX_BIN}" &
  fi
  PIDS+=("$!")
else
  echo "==> MediaMTX not found on PATH; relay mode is unavailable."
  echo "    Install with: brew install mediamtx"
fi

echo "==> Starting camera relay runner..."
uv run --project server tc-camera \
  --width "${CAMERA_WIDTH}" \
  --height "${CAMERA_HEIGHT}" \
  --fps "${CAMERA_FPS}" \
  --startup-timeout "${CAMERA_STARTUP_TIMEOUT}" \
  --retry-interval "${CAMERA_RETRY_INTERVAL}" &
PIDS+=("$!")

echo "==> Starting recorder runner..."
uv run --project server tc-recorder &
PIDS+=("$!")

DEFAULT_RUN_ROBOT_RUNNER="1"
if [[ "${GUI_NO_RERUN}" == "1" ]]; then
  DEFAULT_RUN_ROBOT_RUNNER="0"
fi
RUN_ROBOT_RUNNER_RESOLVED="${RUN_ROBOT_RUNNER:-${DEFAULT_RUN_ROBOT_RUNNER}}"
if [[ "${RUN_ROBOT_RUNNER_RESOLVED}" == "1" ]]; then
  echo "==> Starting robot runner..."
  uv run --project server tc-robot \
    --no-open-browser \
    --rerun-grpc-url "${RERUN_GRPC_URL}" \
    --rerun-web-url "${RERUN_WEB_URL}" \
    --heartbeat-path "${ROBOT_HEARTBEAT_PATH}" &
  PIDS+=("$!")
else
  echo "==> RUN_ROBOT_RUNNER!=1, skipping robot runner (trajectory/3D guard will fail)."
fi

if [[ "${SKIP_CAMERA_GUARD:-0}" != "1" ]]; then
  CAMERA_GUARD_REQUIRE_ROBOT="${CAMERA_GUARD_REQUIRE_ROBOT:-${RUN_ROBOT_RUNNER_RESOLVED}}"
  echo "==> Running camera live guard (WebRTC)..."
  CAMERA_GUARD_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
    CAMERA_GUARD_REQUIRE_ROBOT="${CAMERA_GUARD_REQUIRE_ROBOT}" \
    uv run --project server python scripts/check_camera_live_webrtc.py

  echo "==> Running camera live guard (GUI + snapshot)..."
  if node -e "import('playwright').then(()=>process.exit(0)).catch(()=>process.exit(1))" >/dev/null 2>&1; then
    CAMERA_GUARD_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
      CAMERA_GUARD_GUI_URL="${GUI_URL}" \
      CAMERA_GUARD_GUI_BROWSER="${GUI_GUARD_BROWSER}" \
      node scripts/check_camera_live_gui.mjs
  else
    echo "==> Playwright package not found, skipping GUI snapshot guard."
  fi
else
  echo "==> SKIP_CAMERA_GUARD=1, skipping camera live guards."
fi

wait
