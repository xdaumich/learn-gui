# Telemetry Console

WebRTC camera viewer (OAK-D cameras) + Rerun 3D/2D visualization with synchronized timeline. Designed for monitoring robot arms in real time.

## Repo layout

```
client/                    React + Vite frontend
server/
  telemetry_console/       Python modules (camera, WebRTC, recorder, replay, viewer, API, CLI)
tests/                     All tests (client + server)
scripts/                   Dev and utility scripts
external/                  Reference repos (git submodules, not used at runtime)
```

## Quick start

**Jetson Thor** runs everything. Any machine on the network views the GUI by opening a browser to `http://<thor-ip>:5173`. No code runs on the viewer machine.

```bash
make setup           # install all deps (npm + uv + udev rules)
make find_cameras    # discover OAK cameras (model, device ID, USB speed)
# Edit cameras.json to map device IDs to left/center/right slots
make dev             # start full stack (Vite + FastAPI + camera guard)
```

### Networking

The browser must reach Thor directly by IP (not SSH port-forwarding) for WebRTC video to work. RTP media flows over UDP on dynamically negotiated ports. If on different subnets, use Tailscale or WireGuard.

The frontend auto-derives API URLs from `window.location.hostname` — no env vars needed.

## Camera configuration

### Discovering cameras

```bash
make find_cameras
```

Lists all connected OAK cameras with device ID, model name, USB speed, and sensors:

```
Found 3 OAK camera(s):

  Device ID:  19443010C188E24800
  Model:      OAK-D-W
  USB path:   1.2.1.1.2
  USB speed:  USB 3.0 (Super)
  Sensors:    CAM_A: OV9782 (COLOR/MONO), CAM_B: OV9282 (MONO/COLOR), CAM_C: OV9282 (MONO/COLOR)

  Device ID:  1944301071566F5A00
  Model:      OAK-1-W
  ...
```

### Slot mapping (cameras.json)

Create `cameras.json` in the repo root to assign device IDs to slots:

```json
{
  "left": "<device_id>",
  "center": "<device_id>",
  "right": "<device_id>"
}
```

The OAK-D model should go in the center slot. If `cameras.json` is absent, cameras are assigned automatically with an OAK-D center-slot heuristic.

This file is machine-specific and gitignored.

### Stream settings

Default: **1280x800 @ 30fps**, H.264 Baseline, CBR 4000 kbps.

Override bitrate via `CAMERA_ENCODER_BITRATE_KBPS` env var.

### Wrist camera rotation

Left and right wrist cameras are rotated 90 degrees in the browser (CSS transform, zero server cost) — left rotates clockwise, right counter-clockwise.

## Commands

### Development

```bash
make dev                         # full stack (cleanup -> Vite + FastAPI + camera guard)
SKIP_CAMERA_GUARD=1 make dev     # skip camera guard (no cameras attached)
CAMERA_GUARD_MIN_CAMERAS=2 make dev  # require only 2 cameras
make dev-cleanup                 # kill stale listeners on ports 5173/8000/9876/9090
make find_cameras                # list connected OAK cameras
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

### Video pipeline

```
OAK camera (DepthAI)
  -> H.264 hardware encode on device
  -> aiortc H264Track (in FastAPI process)
  -> Browser (WebRTC via RTCPeerConnection)
```

The browser fetches camera names from `GET /webrtc/cameras`, then does WHEP-style signaling: POST SDP offer to `/webrtc/<camera>/whep`, receive SDP answer, attach video track.

### Camera boot resilience

If a device fails to boot (e.g. USB bandwidth contention on shared hubs), the session manager retries up to 2 times per device then gives up — preventing repeated boot attempts from crashing already-active camera connections.

### Frontend layout

Three display modes (toggled by keyboard shortcuts):

| Mode | Content | Description |
|------|---------|-------------|
| **Zen** | 98% | Bare panels, floating status dot, no chrome |
| **Compact** | 81% | Slim topbar, inline metrics, timeline scrubber |
| **Focus** | 87% | Single panel fills the viewport |

Camera layout: center (hero tile, top) + left/right (wrist tiles, bottom row).

**Keyboard shortcuts:** `Z` (Zen/Compact), `F`/`2` (Focus Rerun), `1` (Focus Camera), `Esc` (back one level).

## Configuration

Copy `.env.example` to `.env` and edit as needed. Most defaults work out of the box.

| Variable | Purpose |
|----------|---------|
| `CAMERA_ENCODER_BITRATE_KBPS` | H.264 encoder bitrate (default: 4000) |
| `MIN_CAMERAS` | Minimum cameras for API startup (default: 3) |
| `CAMERA_GUARD_MIN_CAMERAS` | Minimum cameras for dev guard (default: 3) |
| `CAMERAS_JSON` | Path to camera slot config (default: `cameras.json`) |
| `SKIP_CAMERA_GUARD` | Skip camera guard in `make dev` |
| `GUI_NO_RERUN` | Disable Rerun viewer |
| `DATA_LOG_DIR` | Override recording output path |
| `VITE_API_BASE_URL` | Override FastAPI URL (auto-detected from browser hostname) |

## External references

Code-reference-only submodules under `external/` (not used at runtime):

- **depthai-core** -- Luxonis DepthAI camera SDK
- **rerun** -- Rerun visualization (web viewer + SDK)
- **dexmate-urdf** -- Robot URDF models
- **oak-examples** -- Luxonis OAK example code

Clone them with `make external` if you need to browse the source.
