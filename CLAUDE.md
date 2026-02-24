# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Telemetry Console** — a WebRTC camera viewer (OAK-D cameras) + Rerun 3D/2D visualization viewer with synchronized timeline. Designed for monitoring robot arms (Dexmate vega_1p) in real time and replaying recorded episodes.

## Development workflow

Two-machine setup: **Jetson Thor** runs all backend services, **Mac host** views the web GUI.

| Machine | Role | Runs |
|---------|------|------|
| Jetson Thor | Code, cameras, backend | `make dev_remote` (MediaMTX + tc-camera), `make dev` for full stack |
| Mac host | Web GUI viewer | Browser pointed at Thor's IP |

**Networking:** The browser on Mac must reach Thor directly by IP (not SSH port-forwarding) for WebRTC video to work. WHEP signaling is HTTP, but the actual RTP media flows over UDP on dynamically negotiated ports. TCP-only SSH tunnels block this.

Set client env vars to Thor's LAN IP:
```
VITE_API_BASE_URL=http://<thor-ip>:8000
VITE_WHEP_BASE_URL=http://<thor-ip>:8889
```

If Mac and Thor are on different subnets, use Tailscale or WireGuard for a routed IP with full UDP support.

## Commands

### Setup

```bash
make setup           # install all deps (npm + uv)
make setup_host      # host-only: client + server deps
make setup_remote    # Thor-only: server + mediamtx check
make external        # clone external reference repos (git submodules)
```

### Development

```bash
make dev             # full local stack (cleanup → all runners + camera guard)
SKIP_CAMERA_GUARD=1 make dev    # skip camera guard (no cameras attached)
make dev_host        # host stack: tc-gui + Vite + optional tc-robot
make dev_remote      # Thor stack: mediamtx + tc-camera
make dev-cleanup     # kill stale listeners on ports 5173/8000/9876/9090
```

### Individual runners

```bash
make gui             # tc-gui (FastAPI on :8000)
make camera          # tc-camera (DepthAI relay)
make recorder        # tc-recorder (Zarr recording service)
make replay ARGS="data_logs/<run_id>/<camera>.zarr"
make robot           # standalone robot demo loop + Rerun
make client          # Vite dev server (:5173)
make mediamtx        # MediaMTX relay (:8554 RTSP, :8889 WHEP)
```

Running Python scripts directly:
```bash
uv run --project server python scripts/<script>.py
uv run --project server python scripts/run_camera.py   # local OAK camera window
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

`make dev` starts seven concurrent processes:

| Process | Command | Port |
|---------|---------|------|
| `tc-gui` | FastAPI server | 8000 |
| `tc-camera` | DepthAI → MediaMTX relay | — |
| `tc-recorder` | Zarr recording service | ZMQ 5557 |
| `tc-robot` | Synthetic robot env (optional) | ZMQ 5555 |
| MediaMTX | RTSP/WHEP relay | 8554, 8889 |
| Rerun | gRPC + Web viewer | 9876, 9090 |
| Vite | React frontend | 5173 |

Processes communicate via ZMQ (robot state, recorder control) and MediaMTX (video relay). The FastAPI layer (`tc-gui`) is thin — it proxies requests to subprocess-based services.

### Video pipeline

```
OAK-D camera
  → tc-camera (DepthAI, H.264 hardware encode)
  → MediaMTX (RTSP ingest :8554)
  → Browser (WHEP pull :8889 via RTCPeerConnection)
```

The browser fetches camera names from `GET /webrtc/cameras` (which queries MediaMTX API at `:9997`), then does WHEP signaling: POST SDP offer to `/whep/<camera>/whep`, receive SDP answer, attach video track. This logic lives in [client/src/hooks/useWebRTC.ts](client/src/hooks/useWebRTC.ts).

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
| [server/telemetry_console/cli.py](server/telemetry_console/cli.py) | Entry points (`tc-gui`, `tc-camera`, etc.) |

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

Copy and edit the relevant env file before running:
- `.env.example` → `.env` (local dev)
- `.env.host.example` → `.env.host` (host PC with remote Thor)
- `.env.remote.example` → `.env.remote` (Jetson Thor)

Key client env vars (prefix with `VITE_` for Vite exposure):
- `VITE_API_BASE_URL` — FastAPI server (default `http://localhost:8000`)
- `VITE_WHEP_BASE_URL` — MediaMTX WHEP base (default `http://localhost:8889`)

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
