#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

MEDIAMTX_BIN="${MEDIAMTX_BIN:-$(command -v mediamtx || true)}"

echo "==> Installing server dependencies on remote..."
(cd server && uv sync)

if [[ -z "${MEDIAMTX_BIN}" ]]; then
  echo "ERROR: mediamtx binary not found on PATH." >&2
  echo "Install MediaMTX on Thor, then rerun setup_remote." >&2
  exit 1
fi

echo "==> MediaMTX binary detected at: ${MEDIAMTX_BIN}"
echo "==> Remote setup complete."
