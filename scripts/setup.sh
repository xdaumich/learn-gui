#!/usr/bin/env bash
set -euo pipefail

echo "==> Initializing git submodules..."
git submodule update --init --recursive

echo "==> Installing client dependencies..."
(cd client && npm install)

echo "==> Symlinking node_modules for tests..."
[ -L node_modules ] || ln -s client/node_modules node_modules

echo "==> Installing server dependencies..."
(cd server && uv sync)

echo "==> Done! Run 'make dev' to start."
