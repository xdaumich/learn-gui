.PHONY: \
	setup setup_host setup_remote \
	install_tools install_uv install_mediamtx \
	dev dev-cleanup dev-guard dev_host dev_remote dev_remote_cleanup dev_remove \
	robot client server mediamtx gui camera recorder replay \
	test test-client test-server \
	lint clean

LOCAL_BIN ?= $(HOME)/.local/bin
UV_BIN := $(LOCAL_BIN)/uv
MEDIAMTX_BIN := $(LOCAL_BIN)/mediamtx
MEDIAMTX_LATEST_URL := https://github.com/bluenviron/mediamtx/releases/latest
PATH := $(LOCAL_BIN):$(PATH)
export PATH

setup: install_tools
	@bash scripts/setup.sh

setup_host: install_tools
	@git submodule update --init --recursive
	@cd client && npm install
	@cd server && uv sync

setup_remote: install_tools
	@bash scripts/setup_remote.sh

install_tools: install_uv install_mediamtx

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

install_mediamtx:
	@if command -v mediamtx >/dev/null 2>&1; then \
		echo "==> mediamtx already installed at $$(command -v mediamtx)"; \
	else \
		OS="$$(uname -s)"; \
		ARCH="$$(uname -m)"; \
		case "$$OS" in \
			Darwin) \
				case "$$ARCH" in \
					arm64|aarch64) PLATFORM="darwin_arm64" ;; \
					x86_64|amd64) PLATFORM="darwin_amd64" ;; \
					*) echo "ERROR: Unsupported macOS architecture: $$ARCH" >&2; exit 1 ;; \
				esac ;; \
			Linux) \
				case "$$ARCH" in \
					x86_64|amd64) PLATFORM="linux_amd64" ;; \
					aarch64|arm64) PLATFORM="linux_arm64" ;; \
					*) echo "ERROR: Unsupported Linux architecture: $$ARCH" >&2; exit 1 ;; \
				esac ;; \
			*) echo "ERROR: Unsupported OS for mediamtx install: $$OS" >&2; exit 1 ;; \
		esac; \
		TAG="$$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$(MEDIAMTX_LATEST_URL)" | sed -E 's#.*/##')"; \
		URL="https://github.com/bluenviron/mediamtx/releases/download/$${TAG}/mediamtx_$${TAG}_$${PLATFORM}.tar.gz"; \
		TMP_DIR="$$(mktemp -d)"; \
		trap 'rm -rf "$$TMP_DIR"' EXIT; \
		echo "==> Installing mediamtx from $$URL"; \
		curl -fsSL "$$URL" -o "$$TMP_DIR/mediamtx.tar.gz"; \
		tar -xzf "$$TMP_DIR/mediamtx.tar.gz" -C "$$TMP_DIR" mediamtx; \
		if [ -w "/usr/local/bin" ]; then \
			INSTALL_DIR="/usr/local/bin"; \
		else \
			INSTALL_DIR="$(LOCAL_BIN)"; \
		fi; \
		mkdir -p "$$INSTALL_DIR"; \
		install -m 755 "$$TMP_DIR/mediamtx" "$$INSTALL_DIR/mediamtx"; \
		echo "==> mediamtx installed to $$INSTALL_DIR/mediamtx"; \
	fi
	@if command -v mediamtx >/dev/null 2>&1; then \
		echo "==> mediamtx ready: $$(command -v mediamtx)"; \
	elif [ -x "$(MEDIAMTX_BIN)" ]; then \
		echo "==> mediamtx ready: $(MEDIAMTX_BIN)"; \
	else \
		echo "ERROR: mediamtx installation failed." >&2; \
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

mediamtx:
	mediamtx

gui:
	uv run --project server tc-gui

camera:
	uv run --project server tc-camera

recorder:
	uv run --project server tc-recorder

replay:
	uv run --project server tc-replay $(ARGS)

test: test-client test-server

test-client:
	cd client && npm test

test-server:
	cd server && uv run pytest ../tests/server -v

lint:
	@bash scripts/lint.sh

clean:
	rm -rf client/dist client/node_modules/.vite server/__pycache__ tests/server/__pycache__
