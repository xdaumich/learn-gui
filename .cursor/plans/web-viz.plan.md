---
name: ""
overview: ""
todos: []
isProject: false
---

## 🐛 Bug Fix #15

- 🎯 **Goal:** Fix non-native mode switching — all shortcuts now work from any mode, plus a visible ModeSwitcher UI
- 📝 **Description:** Rewrote `LayoutContext` keyboard handler so `Z`, `F`, `1`, `2`, and `Esc` all work from every mode (previously `F`/`1`/`2` were restricted to compact-only and `Z` broke from focus). Removed the old `toggleZen` helper and `zen-toggle` button. Created a new `ModeSwitcher` segmented pill component with a sliding CSS indicator that shows all three modes (Zen / Compact / Focus) as clickable radio buttons with keyboard-hint badges. Integrated into TopBar (always visible) and FloatingDot (expands on hover in zen mode). Updated README keyboard shortcuts table. Cleaned up unused `.zen-toggle` CSS.
- 🧪 **Test:** `npm --prefix client test -- --run` — pass (3 tests)
- 🔄 **Integration / Regression:** `npm --prefix client test -- --run` — pass (3 tests, all existing assertions unchanged)

## ✨ Feature #14

- 🎯 **Goal:** Simplify and refine the three-mode layout system for clarity, consistency, and maintainability
- 📝 **Description:** Extracted a shared `CompactHeader` component from duplicated compact-header JSX in `VideoPanel` and `RerunPanel` (eliminated ~30 lines of structural duplication). Simplified the `LayoutContext` keyboard shortcut handler from nested `setModeRaw` updaters with inline `setFocusTarget` calls to straightforward if/else using existing `focusPanel`, `exitFocus`, and `setMode` callbacks. Exported `DisplayMode`, `FocusTarget` types and `DEFAULT_SPLIT` constant from `LayoutContext` for reuse; replaced magic number `0.35` in `ResizeHandle` with the shared constant. Consolidated duplicated CSS rules for zen/compact video-panel and rerun-panel sizing into combined selectors. Cleaned up TopBar className concatenation with array-filter-join pattern. All CSS class names preserved for test stability.
- 🧪 **Test:** `npm --prefix client test -- --run` — pass (3 tests)
- 🔄 **Integration / Regression:** `npm --prefix client test -- --run` — pass (3 tests, all existing assertions unchanged)

## 🐛 Bug Fix #13

- 🎯 **Goal:** Simplify the WebRTC reliability code paths without changing behavior
- 📝 **Description:** Refactored the client `useWebRTC` hook to make StrictMode/HMR cancellation guards easier to follow (single `isActive()` gate + small helpers), kept fetch abort + stale-attempt no-op behavior, and streamlined server pipeline state reset/reuse logic while preserving the “don’t reopen device when pipeline is active” rule.
- 🧪 **Test:** `make test-client` — pass (3 vitest)
- 🔄 **Integration / Regression:** `make test` — pass (3 vitest, 9 pytest)

## ✨ Feature #13

- 🎯 **Goal:** Zen / Compact / Focus three-mode layout for maximum camera and rerun content
- 📝 **Description:** Replaced the fixed chrome-heavy layout (43% overhead) with a three-tier density system. **Zen** (default): bare camera + rerun panels fill 98% of the viewport, floating status dot, topbar auto-reveals on hover. **Compact** (press Z): slim 40px topbar, 28px inline panel headers with metrics, 28px timeline scrubber — 81% content. **Focus** (press F/1/2): single panel fills viewport — 87% content. Added `LayoutContext` for mode state + split ratio, `ResizeHandle` for draggable panel divider persisted in localStorage, `FloatingDot` for zen status, and keyboard shortcuts (Z, F, Escape, 1, 2). Rewrote all component rendering to be mode-aware and overhauled App.css for all three modes with 150ms transitions. Updated tests for the new default zen mode.
- 🧪 **Test:** `npm --prefix client test -- --run` — pass (3 tests)
- 🔄 **Integration / Regression:** `make dev` — pass (verified zen, compact, focus modes with live cameras + rerun in browser)

## 🐛 Bug Fix #11

- 🎯 **Goal:** Run the Rerun demo as part of `make dev`
- 📝 **Description:** Updated the dev script to start the Rerun demo alongside the Vite and FastAPI servers, and aligned the README quick-start command to reflect the combined startup.
- 🧪 **Test:** `bash scripts/dev.sh` — not run
- 🔄 **Integration / Regression:** `make test` — not run

## 🐛 Bug Fix #12

- 🎯 **Goal:** Make WebRTC camera streaming reliable during `make dev`
- 📝 **Description:** Avoided reopening the DepthAI device while the streaming pipeline is active (prevents intermittent `X_LINK_*` errors under dev-mode reconnects), reused an active pipeline instead of restarting it per-offer, and removed the `cv2` import from the server process by requesting RGB frames directly.
- 🧪 **Test:** `make dev` — pass (Live Camera shows 3 tiles + “Live connection”; no `InvalidStateError` spam)
- 🔄 **Integration / Regression:** `make test` — pass (3 vitest, 9 pytest)

## 🐛 Bug Fix #10

- 🎯 **Goal:** Ensure the visual tab only shows visual meshes
- 📝 **Description:** Replaced unsupported wildcard query expressions with explicit URDF-root paths so the visual tab includes only `visual_geometries` plus transforms, and the collision tab includes only `collision_geometries` plus transforms. Captured an updated visual-tab snapshot.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py -v` — pass (4 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-vega-visual-tab-v2.png`)

## ✨ Feature #10

- 🎯 **Goal:** Toggle visual vs collision meshes in the 3D viewer
- 📝 **Description:** Replaced the single 3D view with a tabbed container containing Visual and Collision views. Each view filters the opposite geometry root via query expressions, defaulting to the visual tab. Updated blueprint layout tests and captured a visual-tab snapshot.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py -v` — pass (4 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-vega-visual-tab.png`)

## ✨ Feature #9

- 🎯 **Goal:** Load the vega_1p URDF in the Rerun 3D viewer
- 📝 **Description:** Added vega_1p URDF loading during Rerun bridge startup using the built-in loader, plus tests for path resolution and logging. Captured a Playwright snapshot of the embedded viewer with the model visible.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py -v` — pass (4 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-vega-1p.png`; Vite dev server already running on `:5173`)

## ✨ Feature #8

- 🎯 **Goal:** Stack the live camera above a split trajectory + 3D model viewer
- 📝 **Description:** Updated the main grid to a two-row stack, refreshed the Rerun panel copy to reflect the split view, and switched the Rerun blueprint to a horizontal layout with a time-series trajectory on the left and a 3D model view on the right. Captured a refreshed integrated UI snapshot.
- 🧪 **Test:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (captured `rerun-sine-integrated.png`)
- 🔄 **Integration / Regression:** `npm --prefix client test` + `uv run --project server --extra dev python -m pytest tests/server/test_rerun_sine.py -v` — pass (1 vitest, 2 pytest)

## ✨ Feature #10

- 🎯 **Goal:** Stream all connected OAK cameras in the Live Camera panel grid
- 📝 **Description:** Added a `/webrtc/cameras` endpoint to expose connected camera sockets, updated WebRTC negotiation to add one video track per camera, and updated the client hook/UI to request per-camera transceivers and render a grid of video tiles with labels. Added server tests for multi-camera negotiation and camera list, plus client tests for multi-track handling and grid rendering.
- 🧪 **Test:** `npm test -- ../tests/client/useWebRTC.test.tsx` — pass (1 test)
- 🔄 **Integration / Regression:** `uv run pytest ../tests/server/test_webrtc.py ../tests/server/test_webrtc_endpoint.py ../tests/server/test_webrtc_cameras_endpoint.py -v` — pass (3 tests)

## ✨ Feature #9

- 🎯 **Goal:** Stream the RGB OAK camera into the web viewer via P2P WebRTC
- 📝 **Description:** Implemented aiortc DepthAI track and offer handling in `server/webrtc.py`, added `/webrtc/offer` FastAPI signaling with peer connection tracking, built a `useWebRTC` hook for H264-preferred negotiation, and wired `VideoPanel` to auto-connect and render the stream with status UI. Added server/client tests for WebRTC negotiation and hook behavior.
- 🧪 **Test:** `bash scripts/dev.sh` — pass (UI shows Live connection; snapshot saved to `artifacts/webrtc-live-rgb.png`; no camera image without attached OAK device)
- 🔄 **Integration / Regression:** `make test-server` — pass (6 tests)

## 🐛 Bug Fix #9

- 🎯 **Goal:** Make the Rerun plot fill the viewer window in the embedded iframe
- 📝 **Description:** Updated `.media-placeholder.is-rerun` styling to stretch grid items, remove padding, and hide overflow, plus added `.rerun-iframe` and `.placeholder-overlay` styles so the iframe fills the panel and the loading overlay sits on top. Updated `RerunPanel` to use the new iframe class. The embedded Rerun plot now fills the full viewer window instead of rendering at a small size.
- 🧪 **Test:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-sine-fill.png` shows the plot fills the viewer area)
- 🔄 **Integration / Regression:** `N/A` — no automated regression run for this UI-only tweak

## ✨ Feature #7

- 🎯 **Goal:** Track Luxonis OAK examples as an external submodule
- 📝 **Description:** Added `external/oak-examples` as a git submodule pointing at `https://github.com/luxonis/oak-examples` to keep the upstream examples synced without vendoring the repo.
- 🧪 **Test:** `git submodule status external/oak-examples` — not run
- 🔄 **Integration / Regression:** `git submodule update --init --recursive` — not run

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

