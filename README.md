# Telemetry Console

WebRTC camera viewer + Rerun trajectory viewer with synchronized timeline.

## Repo layout

```
client/                    React + Vite frontend
server/
  telemetry_console/       Split SDK/runtime modules (viewer, camera, env, recorder, replay, GUI API, CLI)
  main.py                  Backward-compat API entry point (delegates to telemetry_console.gui_api)
tests/                     All tests (client + server)
external/                  Reference repos (git submodules, not used at runtime)
scripts/                   Dev scripts (setup, dev, lint)
```

## Quick start

```bash
make setup       # install all deps (npm + uv)
make dev         # clean stale ports, start split runners, run camera guards
make test        # run all tests
make external    # clone external reference repos (git submodules, optional)
```

## Usage (Thor camera + host UI)

Use this profile when OAK cameras are connected to Jetson Thor and the app runs on a host PC.

### 1) First-time setup

On Thor:

```bash
cd /Users/xda/Projects/learn-gui
cp .env.remote.example .env.remote
set -a; source .env.remote; set +a
make setup_remote
```

On host:

```bash
cd /Users/xda/Projects/learn-gui
cp .env.host.example .env.host
# Set THOR_IP in .env.host (recommended), or pass THOR_IP inline when running make.
set -a; source .env.host; set +a
make setup_host
```

### 2) Daily run

Start remote media/camera services on Thor (keep this terminal running):

```bash
cd /Users/xda/Projects/learn-gui
set -a; source .env.remote; set +a
make dev_remote
```

Start GUI/frontend on host (keep this terminal running):

```bash
cd /Users/xda/Projects/learn-gui
set -a; source .env.host; set +a
make dev_host
```

If `THOR_IP` is not set in `.env.host`, run:

```bash
THOR_IP=<thor-ip> make dev_host
```

### 3) Verify

On host:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/webrtc/cameras
```

Open:

```text
http://localhost:5173
```

Expected result: one live tile per camera streamed from Thor MediaMTX WHEP (`http://<thor-ip>:8889/<camera>/whep`).

### 4) Cleanup and recovery

On Thor:

```bash
make dev_remote_cleanup
make dev_remove      # alias of make dev_remote
```

### 5) Wi-Fi fallback

If Ethernet/Wi-Fi bandwidth is limited, lower camera load in `.env.remote`:

- `CAMERA_FPS=20`
- `CAMERA_WIDTH=640`
- `CAMERA_HEIGHT=360`

## Runtime model

`make dev` runs a split runner stack:

- `tc-gui` (FastAPI + Rerun viewer)
- `tc-camera` (DepthAI to MediaMTX relay)
- `tc-recorder` (recording service)
- MediaMTX relay
- Vite frontend

Robot runner starts by default in dev startup (disable with `RUN_ROBOT_RUNNER=0 make dev`).

## Individual commands

```bash
make test-client   # vitest only
make test-server   # pytest only
make dev-cleanup   # kill stale dev listeners on 5173/8000/9876/9090 only
make dev-guard     # run camera live guard checks against a running stack
make setup_host    # install host dependencies (client + server)
make setup_remote  # install remote dependencies (server + mediamtx check)
make dev_host      # host-only stack (tc-gui + Vite + optional tc-robot)
make dev_remote    # remote-only stack (mediamtx + tc-camera)
make dev_remote_cleanup  # clean remote media ports/processes
make dev_remove    # alias for dev_remote
make gui           # start tc-gui
make camera        # start tc-camera
make recorder      # start tc-recorder
make replay ARGS="data_logs/<run_id>/<camera>.zarr"   # replay logs
make robot         # run standalone robot demo loop
make lint          # ruff + tsc
make clean         # remove build artifacts
uv run --project server python scripts/run_camera.py  # local OAK camera windows
```

## Camera live guard

`make dev` now runs a regression guard that checks camera readiness across:

- API discovery (`/health`, `/webrtc/cameras`)
- Relay path readiness (MediaMTX API `/v3/paths/list`)
- GUI rendering (headless browser validates live tiles)

If any camera is not live before timeout, `make dev` exits non-zero and prints
an error. The GUI guard also saves verification snapshots:

- `docs/assets/screenshots/camera-live-guard-success.png`
- `docs/assets/screenshots/camera-live-guard-failure.png`

To bypass guards intentionally (for environments without cameras):

```bash
SKIP_CAMERA_GUARD=1 make dev
```

## GUI usage

The viewer opens in **Zen mode** by default — camera and Rerun panels fill the
screen with no controls visible. Three display modes let you trade information
density for content area:

| Mode        | Content | Description                                      |
|-------------|---------|--------------------------------------------------|
| **Zen**     | 98%     | Bare panels, floating status dot, no chrome       |
| **Compact** | 81%     | Slim topbar, inline metrics, timeline scrubber    |
| **Focus**   | 87%     | Single panel fills the viewport                   |

### Keyboard shortcuts

All shortcuts work from **any** mode — no need to be in a specific mode first.

| Key     | Action                                               |
|---------|------------------------------------------------------|
| `Z`     | Toggle Zen ↔ Compact (from Focus goes to Zen)        |
| `F`     | Toggle Focus on Rerun (from any mode)                |
| `1`     | Toggle Focus on Camera (from any mode)               |
| `2`     | Toggle Focus on Rerun (from any mode)                |
| `Esc`   | Go back one level: Focus → Compact → Zen             |

### Mouse interactions

- **Hover top edge** in Zen mode to temporarily reveal the topbar
- **Drag the resize handle** between panels to adjust the split (persisted)
- **Double-click the resize handle** to reset to the default 35/65 split
- **Click the floating dot** (bottom-right in Zen) to enter Compact mode

## Recording logs (Zarr)

Click **Rec** in the topbar to start logging the live camera stream alongside
a synthetic sine trajectory. Click **Stop** to end the run.

By default logs are written to:

```
data_logs/<run_id>/<camera>.zarr/
```

Set `DATA_LOG_DIR` to override the output path.

Camera relay defaults to device-side `H264` for broad browser compatibility
(Chrome, Firefox, Safari). The host stays relay-only for streaming and only
decodes on the recording path when recording is active.

## External references

Code-reference-only submodules under `external/` (not used at runtime):

- **depthai-core** -- Luxonis DepthAI camera SDK
- **rerun** -- Rerun visualization (web viewer + SDK)
- **dexmate-urdf** -- Robot URDF models
- **oak-examples** -- Luxonis OAK example code

Clone them with `make external` if you need to browse the source.
