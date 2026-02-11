#!/usr/bin/env bash
set -euo pipefail

PIDS=()
VITE_PORT="${VITE_PORT:-5173}"
API_PORT="${API_PORT:-8000}"
GUI_URL="${CAMERA_GUARD_GUI_URL:-http://localhost:${VITE_PORT}}"

cleanup() {
  local exit_code=$?
  trap - EXIT SIGINT SIGTERM
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  # Ensure grandchildren (uvicorn reloader/vite worker) are also terminated.
  kill 0 >/dev/null 2>&1 || true
  wait >/dev/null 2>&1 || true
  exit "$exit_code"
}

trap cleanup EXIT SIGINT SIGTERM

require_free_port() {
  local port="$1"
  local name="$2"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: ${name} port ${port} is already in use. Stop existing process first." >&2
    exit 1
  fi
}

require_free_port "${VITE_PORT}" "Vite"
require_free_port "${API_PORT}" "FastAPI"

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
