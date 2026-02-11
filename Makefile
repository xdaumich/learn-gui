.PHONY: setup dev dev-cleanup dev-guard test test-client test-server lint clean

setup:
	@bash scripts/setup.sh

dev: dev-cleanup
	@DEV_SKIP_PRE_CLEANUP=1 bash scripts/dev.sh

dev-cleanup:
	@bash scripts/dev.sh --cleanup-only

dev-guard:
	uv run --project server python scripts/check_camera_live_webrtc.py && \
		node scripts/check_camera_live_gui.mjs

test: test-client test-server

test-client:
	cd client && npm test

test-server:
	cd server && uv run pytest ../tests/server -v

lint:
	@bash scripts/lint.sh

clean:
	rm -rf client/dist client/node_modules/.vite server/__pycache__ tests/server/__pycache__
