---
name: ""
overview: ""
todos: []
isProject: false
---

## ✨ Feature #6

- 🎯 **Goal:** Stream a live sine-wave trajectory in the Rerun Web Viewer embedded in the frontend
- 📝 **Description:** Implemented `server/rerun_bridge.py` with `start()` (inits Rerun, starts gRPC on port 9876, web viewer on 9090, sends a `TimeSeriesView` blueprint with a rolling 2-second `VisibleTimeRange`) and `stream_sine_wave()` (logs `sin`/`cos` scalars at 20 Hz using wall-clock `timestamp`). Created `scripts/run_rerun_demo.py` as a standalone entry point that re-execs into the server venv. Updated `client/src/components/RerunPanel.tsx` to embed the Rerun web viewer via `<iframe>` with auto-connect query param (`?url=rerun%2Bhttp://localhost:9876/proxy`). Added `GET /rerun/status` endpoint to `server/main.py`. Added `tests/server/test_rerun_sine.py` to verify bridge startup, port availability, and streaming.
- 🧪 **Test:** `cd server && uv run pytest ../tests/server/test_rerun_sine.py -v` — pass (1 test); Playwright verification: Rerun viewer direct page shows live sin/cos plot with 2-sec rolling window on `wall_time` timeline; integrated app at `localhost:5173` renders the Rerun iframe with the live trajectory.
- 🔄 **Integration / Regression:** `cd server && uv run pytest ../tests/server/test_server.py ../tests/server/test_rerun_sine.py -v` — pass (2 tests)

## 🐛 Bug Fix #8

- 🎯 **Goal:** Install OpenCV dependency for camera script
- 📝 **Description:** Added `opencv-python` to `server/pyproject.toml` so `scripts/run_camera.py` can import `cv2` when run via uv.
- 🧪 **Test:** `uv run --project server python scripts/run_camera.py` — not run
- 🔄 **Integration / Regression:** `make test-server` — not run

## 🐛 Bug Fix #7

- 🎯 **Goal:** Remove uv warning about exact Python version pin
- 📝 **Description:** Updated `server/pyproject.toml` to use `==3.10.*` for `requires-python`, matching uv's guidance to include a patch wildcard instead of an exact minor pin.
- 🧪 **Test:** `uv run --project server python scripts/run_camera.py` — not run
- 🔄 **Integration / Regression:** `make test-server` — not run

## 🐛 Bug Fix #6

- 🎯 **Goal:** Install all external submodules during setup
- 📝 **Description:** Added setup steps to install DepthAI requirements from `external/depthai-core`, plus editable installs for `external/rerun/rerun_py` and `external/dexmate-urdf`. Added `dexmate-urdf` to `server/pyproject.toml` so the server venv tracks the dependency explicitly.
- 🧪 **Test:** `bash scripts/setup.sh` — not run
- 🔄 **Integration / Regression:** `make setup` — not run

## 🐛 Bug Fix #5

- 🎯 **Goal:** Install external dependencies (depthai-core) during setup
- 📝 **Description:** `scripts/setup.sh` was not installing the DepthAI library from the `external/depthai-core` submodule. Added `server/.venv/bin/pip install depthai --force-reinstall` after `uv sync` to ensure the latest DepthAI wheel is properly installed in the server venv, following [Luxonis install docs](https://docs.luxonis.com/software-v3/depthai/).
- 🧪 **Test:** `bash scripts/setup.sh` — not run
- 🔄 **Integration / Regression:** `make setup` — not run

## ✨ Feature #5

- 🎯 **Goal:** Add a DepthAI camera streaming script with full environment setup
- 📝 **Description:** Created `scripts/run_camera.py` mirroring `external/depthai-core/examples/python/Camera/camera_all.py`. It discovers all connected OAK cameras, opens a full-resolution output queue per sensor, and displays each feed in an OpenCV window (press `q` to quit). Added `opencv-python` and `depthai` to server dependencies with a pytest import check. Updated `scripts/setup.sh` to source the server venv after `uv sync` so it is active without manual steps.
- 🧪 **Test:** `make test-server` — pass (2 tests); `server/.venv/bin/python scripts/run_camera.py` — requires physical OAK device
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_camera.py` — requires physical OAK device

## ✨ Feature #4

- 🎯 **Goal:** Restructure repo into professional client/server/tests layout
- 📝 **Description:** Reorganized flat repo into `client/` (React+Vite), `server/` (FastAPI), `tests/` (client+server), `external/` (submodules), `scripts/` (setup/dev/lint). Decomposed monolithic App.tsx into per-component files. Added Makefile with setup/dev/test/lint/clean targets. Created FastAPI server scaffold with signaling schemas. Symlinked root node_modules for cross-directory test resolution.
- 🧪 **Test:** `make test-client` — pass (1 test, vitest)
- 🔄 **Integration / Regression:** `make test-client` — pass

## ✨ Feature #3

- 🎯 **Goal:** Document how to run the frontend GUI
- 📝 **Description:** Run `npm install` then `npm run dev` from the repo root, open the printed local URL in a browser.
- 🧪 **Test:** `N/A` — not run (documentation only)
- 🔄 **Integration / Regression:** `N/A` — not run

## ✨ Feature #2

- 🎯 **Goal:** Scaffold the Version A frontend layout with placeholders
- 📝 **Description:** Build a two-panel WebRTC/Rerun shell with top controls, status pills, and a timeline bar, plus a test-backed UI scaffold.
- 🧪 **Test:** `npm test` — pass (vitest)
- 🔄 **Integration / Regression:** `N/A` — not run

## ✨ Feature #1

- 🎯 **Goal:** Prepare Python env and external deps with uv and submodules
- 📝 **Description:** Add uv setup instructions, requirements.txt, and track depthai-core, rerun, dexmate-urdf as git submodules under external_dependencies with a README
- 🧪 **Test:** `N/A` — not run (env setup only)
- 🔄 **Integration / Regression:** `N/A` — not run
