#!/usr/bin/env bash
set -euo pipefail

echo "==> Linting server (ruff)..."
(cd server && uv run ruff check .)

echo "==> Type-checking client (tsc)..."
(cd client && npx tsc --noEmit)

echo "==> All clean."
