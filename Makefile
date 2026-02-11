.PHONY: setup setup_host setup_remote dev dev-cleanup dev-guard dev_host dev_remote dev_remote_cleanup dev_remove robot client server mediamtx gui camera recorder replay test test-client test-server lint clean

setup:
	@bash scripts/setup.sh

setup_host:
	@git submodule update --init --recursive
	@cd client && npm install
	@cd server && uv sync

setup_remote:
	@bash scripts/setup_remote.sh

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
