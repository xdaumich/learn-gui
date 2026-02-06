.PHONY: setup dev test test-client test-server lint clean

setup:
	@bash scripts/setup.sh

dev:
	@bash scripts/dev.sh

test: test-client test-server

test-client:
	cd client && npm test

test-server:
	cd server && uv run pytest ../tests/server -v

lint:
	@bash scripts/lint.sh

clean:
	rm -rf client/dist client/node_modules/.vite server/__pycache__ tests/server/__pycache__
