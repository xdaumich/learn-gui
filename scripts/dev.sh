#!/usr/bin/env bash
set -euo pipefail

# Start both client and server; kill both on Ctrl+C
trap 'kill 0; exit' SIGINT SIGTERM

echo "==> Starting client (Vite)..."
(cd client && npm run dev) &

echo "==> Starting server (FastAPI)..."
(cd server && uv run uvicorn main:app --reload --port 8000) &

wait
