# Telemetry Console

WebRTC camera viewer + Rerun trajectory viewer with synchronized timeline.

## Repo layout

```
client/          React + Vite frontend
server/          FastAPI backend (WebRTC signaling, Rerun bridge)
tests/           All tests (client + server)
external/        Git submodules (depthai-core, rerun, dexmate-urdf)
scripts/         Dev scripts (setup, dev, lint)
```

## Quick start

```bash
make setup       # install all deps (npm + uv + submodules)
make dev         # clean stale dev ports/processes, then start stack + camera guards
make test        # run all tests
```

## Individual commands

```bash
make test-client   # vitest only
make test-server   # pytest only
make dev-cleanup   # kill stale dev listeners on 5173/8000/9876/9090 only
make dev-guard     # run camera live guard checks against a running stack
make lint          # ruff + tsc
make clean         # remove build artifacts
uv run --project server python scripts/run_camera.py  # local OAK camera windows
```

## Camera live guard

`make dev` now runs a regression guard that checks camera readiness across:

- API discovery (`/health`, `/webrtc/cameras`)
- WebRTC frame delivery (`/webrtc/offer`)
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

## External dependencies

Tracked as git submodules under `external/`:

- **depthai-core** -- Luxonis DepthAI camera SDK
- **rerun** -- Rerun visualization (web viewer + SDK)
- **dexmate-urdf** -- Robot URDF models
