.PHONY: \
	setup setup_host setup_remote external \
	install_tools install_uv \
	dev dev-cleanup dev-guard dev_host dev_remote dev_remote_cleanup dev_remove \
	robot client server gui recorder replay mjpeg \
	test test-client test-server test-integration \
	lint clean

LOCAL_BIN ?= $(HOME)/.local/bin
UV_BIN := $(LOCAL_BIN)/uv
PATH := $(LOCAL_BIN):$(PATH)
export PATH

setup: install_tools
	@bash scripts/setup.sh

setup_host: install_tools
	@cd client && npm install
	@cd server && uv sync

setup_remote: install_tools
	@bash scripts/setup_remote.sh

external:
	@echo "==> Cloning external reference repos (submodules)..."
	@git submodule update --init --recursive

install_tools: install_uv

install_uv:
	@if command -v uv >/dev/null 2>&1; then \
		echo "==> uv already installed at $$(command -v uv)"; \
	else \
		echo "==> Installing uv into $(LOCAL_BIN)..."; \
		mkdir -p "$(LOCAL_BIN)"; \
		curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$(LOCAL_BIN)" sh; \
	fi
	@if command -v uv >/dev/null 2>&1; then \
		echo "==> uv ready: $$(command -v uv)"; \
	elif [ -x "$(UV_BIN)" ]; then \
		echo "==> uv ready: $(UV_BIN)"; \
	else \
		echo "ERROR: uv installation failed." >&2; \
		exit 1; \
	fi

dev: dev-cleanup
	@DEV_SKIP_PRE_CLEANUP=1 bash scripts/dev.sh

dev-cleanup:
	@bash scripts/dev.sh --cleanup-only

dev_host:
	@bash scripts/dev_host.sh

dev_remote:
	@bash scripts/dev_remote.sh

dev_remove: dev_remote

dev_remote_cleanup:
	@bash scripts/dev_remote.sh --cleanup-only

dev-guard:
	uv run --project server python scripts/check_camera_live_webrtc.py && \
		node scripts/check_camera_live_gui.mjs

robot:
	-pkill -f 'run_robot\.py' 2>/dev/null; sleep 0.5
	uv run --project server python scripts/run_robot.py --no-open-browser

client:
	cd client && npm run dev

server:
	cd server && uv run uvicorn main:app --reload --port 8000

gui:
	uv run --project server tc-gui

recorder:
	uv run --project server tc-recorder

replay:
	uv run --project server tc-replay $(ARGS)

mjpeg:
	uv run --project server python scripts/mjpeg_debug.py

test: test-client test-server

test-client:
	cd client && npm test

test-server:
	cd server && uv run --extra dev pytest ../tests/server -v

test-integration:
	cd client && npx playwright test --config ../tests/integration/playwright.config.ts

lint:
	@bash scripts/lint.sh

clean:
	rm -rf client/dist client/node_modules/.vite server/__pycache__ tests/server/__pycache__
