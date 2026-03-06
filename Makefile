.PHONY: \
	setup external \
	install_tools install_uv install_npm install_udev_rules \
	dev dev-cleanup dev-guard find_cameras \
	robot client server gui recorder replay mjpeg mjpeg_elp \
	test test-client test-server test-integration \
	lint clean

LOCAL_BIN ?= $(HOME)/.local/bin
UV_BIN := $(LOCAL_BIN)/uv
PATH := $(LOCAL_BIN):$(PATH)
export PATH

setup: install_tools
	@bash scripts/setup.sh

external:
	@echo "==> Cloning external reference repos (submodules)..."
	@git submodule update --init --recursive

install_tools: install_uv install_npm install_udev_rules

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

install_npm:
	@if command -v npm >/dev/null 2>&1; then \
		echo "==> npm already installed at $$(command -v npm)"; \
	elif command -v apt-get >/dev/null 2>&1; then \
		echo "==> Installing Node.js/npm via apt-get..."; \
		if [ "$$(id -u)" -eq 0 ]; then \
			apt-get update && apt-get install -y nodejs npm; \
		elif command -v sudo >/dev/null 2>&1; then \
			sudo apt-get update && sudo apt-get install -y nodejs npm; \
		else \
			echo "ERROR: npm missing and sudo not available for apt-get install." >&2; \
			exit 1; \
		fi; \
	else \
		echo "ERROR: npm not found and no supported package manager bootstrap configured." >&2; \
		exit 1; \
	fi
	@if command -v npm >/dev/null 2>&1; then \
		echo "==> npm ready: $$(command -v npm)"; \
	else \
		echo "ERROR: npm installation failed." >&2; \
		exit 1; \
	fi

install_udev_rules:
	@if [ "$$(uname -s)" != "Linux" ]; then \
		echo "==> Non-Linux platform detected; skipping DepthAI udev rule setup."; \
	elif [ -f /etc/udev/rules.d/80-movidius.rules ]; then \
		echo "==> DepthAI udev rules already present at /etc/udev/rules.d/80-movidius.rules"; \
	elif command -v sudo >/dev/null 2>&1; then \
		echo "==> Installing DepthAI udev rules..."; \
		sudo sh -c 'printf "%s\n" "# Luxonis/DepthAI OAK cameras (Movidius/MyriadX and FTDI interfaces)" "SUBSYSTEM==\"usb\", ATTR{idVendor}==\"03e7\", MODE=\"0666\"" "SUBSYSTEM==\"usb\", ATTR{idVendor}==\"0403\", MODE=\"0666\"" > /etc/udev/rules.d/80-movidius.rules'; \
		sudo chmod 644 /etc/udev/rules.d/80-movidius.rules; \
		sudo udevadm control --reload-rules; \
		sudo udevadm trigger --subsystem-match=usb --action=add; \
		echo "==> DepthAI udev rules installed."; \
	else \
		echo "==> WARNING: sudo not available; skipping DepthAI udev rule install."; \
	fi


dev: dev-cleanup
	@DEV_SKIP_PRE_CLEANUP=1 bash scripts/dev.sh

dev-cleanup:
	@bash scripts/dev.sh --cleanup-only

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

mjpeg_elp:
	uv run --project server python scripts/mjpeg_elp.py

find_cameras:
	uv run --project server python scripts/find_cameras.py

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
