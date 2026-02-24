#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing client dependencies..."
(cd client && npm install)

if [[ "${SKIP_PLAYWRIGHT_INSTALL:-0}" != "1" ]]; then
  echo "==> Installing Playwright Chromium runtime..."
  (cd client && npx playwright install chromium)
else
  echo "==> SKIP_PLAYWRIGHT_INSTALL=1, skipping Playwright browser install."
fi

echo "==> Installing server dependencies..."
(cd server && uv sync)

echo "==> Done! Run 'make dev' to start."
