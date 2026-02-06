---
name: ""
overview: ""
todos: []
isProject: false
---

## ✨ Feature #5

- 🎯 **Goal:** Add a DepthAI camera streaming script
- 📝 **Description:** Created `scripts/run_camera.py` mirroring `external/depthai-core/examples/python/Camera/camera_all.py`. It discovers all connected OAK cameras, opens a full-resolution output queue per sensor, and displays each feed in an OpenCV window. Press `q` to quit.
- 🧪 **Test:** `python scripts/run_camera.py` — requires physical OAK device
- 🔄 **Integration / Regression:** `python scripts/run_camera.py` — not run

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
