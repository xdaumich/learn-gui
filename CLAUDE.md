# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Telemetry Console** — a WebRTC camera viewer (OAK-D cameras) + Rerun 3D/2D visualization viewer with synchronized timeline. Designed for monitoring robot arms (Dexmate vega_1p) in real time and replaying recorded episodes.

## Development workflow

**Jetson Thor** runs everything (`make dev`). Any machine on the network views the GUI by opening a browser to `http://<thor-ip>:5173`. No code runs on the viewer machine.

**Networking:** The browser must reach Thor directly by IP (not SSH port-forwarding) for WebRTC video to work. RTP media flows over UDP on dynamically negotiated ports — TCP-only SSH tunnels block this. If on different subnets, use Tailscale or WireGuard.

URL auto-detection: the frontend derives API/Rerun URLs from `window.location.hostname`, so no env vars are needed. Override with `VITE_API_BASE_URL` if necessary.

## Commands

### Setup

```bash
make setup           # install all deps (npm + uv)
make external        # clone external reference repos (git submodules)
```

### Development

```bash
make dev             # full stack (cleanup → Vite + FastAPI + camera guard)
SKIP_CAMERA_GUARD=1 make dev    # skip camera guard (no cameras attached)
make dev-cleanup     # kill stale listeners on ports 5173/8000/9876/9090
```

### Individual runners

```bash
make gui             # tc-gui (FastAPI on :8000, opens cameras via aiortc)
make recorder        # tc-recorder (Zarr recording service)
make replay ARGS="data_logs/<run_id>/<camera>.zarr"
make robot           # standalone robot demo loop + Rerun
make client          # Vite dev server (:5173)
make mjpeg           # MJPEG debug server for OAK cameras (:8001)
make mjpeg_elp       # MJPEG debug server for ELP cameras (:8002)
```

Running Python scripts directly:
```bash
uv run --project server python scripts/<script>.py
```

### Testing

```bash
make test            # all tests (client + server)
make test-client     # vitest only
make test-server     # pytest only (verbose)

# Single test file:
cd client && npx vitest run tests/client/useWebRTC.test.tsx
cd server && uv run --extra dev pytest ../tests/server/test_gui_api.py -v
# Single test by name:
cd server && uv run --extra dev pytest ../tests/server/test_gui_api.py::test_health -v
```

### Integration test requirement

For every new feature or milestone:
1. `make dev` — confirm the full stack boots and camera guard passes (includes video decode check).
2. `make test` — all unit tests must pass.
3. `make test-integration` — run Playwright integration tests against the live stack (requires `make dev` running).

### Lint

```bash
make lint            # ruff (Python) + tsc (TypeScript)
```

## Architecture

### Runtime model

`make dev` starts these concurrent processes:

| Process | Command | Port |
|---------|---------|------|
| `tc-gui` | FastAPI server + aiortc WebRTC | 8000 |
| `tc-recorder` | Zarr recording service (optional) | ZMQ 5557 |
| `tc-robot` | Synthetic robot env (optional) | ZMQ 5555 |
| Rerun | gRPC + Web viewer (optional) | 9876, 9090 |
| Vite | React frontend | 5173 |

Processes communicate via ZMQ (robot state, recorder control). FastAPI (`tc-gui`) handles cameras directly via DepthAI + aiortc — no MediaMTX needed.

### Video pipeline

```
OAK-D camera
  → DepthAI H.264 hardware encode
  → aiortc H264Track (in FastAPI process)
  → Browser (WebRTC via RTCPeerConnection)
```

The browser fetches camera names from `GET /webrtc/cameras`, then does WHEP-style signaling: POST SDP offer to `/webrtc/<camera>/whep`, receive SDP answer, attach video track. All signaling goes through FastAPI (aiortc). This logic lives in [client/src/hooks/useWebRTC.ts](client/src/hooks/useWebRTC.ts).

Camera socket ordering in [server/telemetry_console/camera.py](server/telemetry_console/camera.py): `CAM_B=left`, `CAM_A=center`, `CAM_C=right`. OAK-D (RGB-preferred) model gets center slot priority.

### Frontend layout

Three display modes (toggled by keyboard shortcuts):
- **Zen** (98% content): no topbar, floating status dot
- **Compact** (81%): slim topbar, metrics, timeline scrubber
- **Focus** (87%): single panel fills viewport

Global UI state lives in [client/src/contexts/LayoutContext.tsx](client/src/contexts/LayoutContext.tsx). Split ratio is persisted in `localStorage`.

Keyboard shortcuts: `Z` (Zen↔Compact), `F`/`2` (Focus Rerun), `1` (Focus Camera), `Esc` (back one level).

### Backend modules

| Module | Purpose |
|--------|---------|
| [server/telemetry_console/gui_api.py](server/telemetry_console/gui_api.py) | FastAPI endpoints |
| [server/telemetry_console/camera.py](server/telemetry_console/camera.py) | DepthAI relay manager |
| [server/telemetry_console/recorder.py](server/telemetry_console/recorder.py) | Zarr recording (ZMQ-controlled) |
| [server/telemetry_console/replay.py](server/telemetry_console/replay.py) | Zarr reader + Rerun playback |
| [server/telemetry_console/viewer.py](server/telemetry_console/viewer.py) | Rerun server lifecycle + URDF + blueprints |
| [server/telemetry_console/env.py](server/telemetry_console/env.py) | Gym-like RobotEnv + ZMQ PUB |
| [server/telemetry_console/zmq_channels.py](server/telemetry_console/zmq_channels.py) | ZMQ port constants + msgpack serialization |
| [server/telemetry_console/webrtc_sessions.py](server/telemetry_console/webrtc_sessions.py) | aiortc WebRTC session manager |
| [server/telemetry_console/webrtc_track.py](server/telemetry_console/webrtc_track.py) | H.264 track for aiortc |
| [server/telemetry_console/cli.py](server/telemetry_console/cli.py) | Entry points (`tc-gui`, `tc-robot`, etc.) |

### ZMQ IPC

| Channel | Port | Direction |
|---------|------|-----------|
| ROBOT_STATE | 5555 | PUB from RobotEnv |
| RECORDER_STATUS | 5556 | PUB from Recorder |
| RECORDER_CONTROL | 5557 | REP/REQ (recorder responds, API requests) |

Serialization: msgpack (binary).

### Recording (Zarr)

`ZarrEpisodeLogger` in [server/data_log.py](server/data_log.py) writes append-only time-series:
- Arrays: `rgb` (H×W×3 uint8), `t_ns` (int64), `ee_pose` (7×float32)
- Compression: Blosc zstd clevel=3, bitshuffle
- Output: `data_logs/<run_id>/<camera>.zarr/`  (override with `DATA_LOG_DIR`)

## Configuration

Copy `.env.example` → `.env` and edit as needed. Most defaults work out of the box.

The frontend auto-derives backend URLs from the browser's `window.location.hostname` — no client env vars needed. To override:
- `VITE_API_BASE_URL` — FastAPI server (auto-detected from browser hostname, port 8000)

## Plan tracking

For every feature or bug fix, add an entry at the **top** of [.cursor/plans/web-viz.plan.md](.cursor/plans/web-viz.plan.md) using:

```markdown
## ✨ Feature #N | 🐛 Bug Fix #N

- 🎯 **Goal:** <what this change achieves>
- 📝 **Description:** <implementation details>
- 🧪 **Test:** `<exact command>` — <pass/fail + summary>
- 🔄 **Integration / Regression:** `<exact command>` — <pass/fail + summary>
```

## Video streaming verification

After any change to `VideoPanel.tsx`, `useWebRTC.ts`, or camera/WebRTC pipeline code, run `make test-client` and confirm **all of the following assertions pass**:

| Assertion | Test name |
|-----------|-----------|
| Three `<video data-testid="camera-stream">` elements rendered | "renders three camera tiles for left/center/right" |
| `video.play()` called ≥ 3 times (once per tile) | "calls play() on each video element when stream is attached" |
| Each `video.srcObject.getVideoTracks()[0].readyState === "live"` | "each video stream has a live-state video track" |
| Labels Left / Center / Right in that order | "video tiles display ordered labels left/center/right" |
| No `role="alert"` banner when all 3 cameras present | "no error banner when all three cameras are streaming" |

For real playback validation (requires full stack + cameras):
```bash
make dev   # stack must be running
node scripts/check_camera_live_gui.mjs
# PASS = 3/3 tiles have readyState ≥ 2 AND currentTime is advancing
```

`check_camera_live_gui.mjs` is the authoritative end-to-end check — it verifies decoded frames are actually advancing, not just that the WebRTC connection is open.

## Asset storage

Screenshots and UI snapshots go under `docs/assets/` (e.g. `docs/assets/screenshots/`). Never place them at the repo root.
