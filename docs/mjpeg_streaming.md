# MJPEG Debug Streaming

Standalone MJPEG server for debugging camera connectivity without WebRTC/MediaMTX.

## Motivation

The WebRTC pipeline (DepthAI → FFmpeg → MediaMTX RTSP → WHEP → browser) has many
failure points: ICE negotiation, SDP exchange, UDP port allocation, MediaMTX config,
H.264 codec support. When video doesn't appear, it's hard to tell if the problem is
the camera or the delivery layer.

MJPEG over HTTP eliminates all of that. If MJPEG works but WebRTC doesn't, the
cameras are fine and the problem is in the relay/signaling stack.

## Design

### What

`scripts/mjpeg_debug.py` — a self-contained FastAPI server that streams MJPEG from
connected OAK cameras over plain HTTP. No dependency on tc-camera, MediaMTX, tc-gui,
or any other service.

### Endpoints

| Method | Path | Response |
|--------|------|----------|
| `GET /` | HTML page with `<img>` tags for all discovered cameras | `text/html` |
| `GET /stream/{camera}` | Single camera MJPEG stream | `multipart/x-mixed-replace` |
| `GET /cameras` | JSON list of discovered camera names | `application/json` |

### Pipeline

```
OAK-D camera
  → DepthAI ColorCamera (preview output)
  → DepthAI VideoEncoder (MJPEG profile, on-device)
  → XLinkOut queue
  → HTTP multipart/x-mixed-replace boundary stream
```

No FFmpeg. No RTSP. No transcoding on the host. The OAK chip does JPEG encoding
in hardware.

### Device discovery

Reuses the same ordering logic as `camera.py`:

1. Enumerate connected DepthAI devices.
2. Sort: OAK-D models get center priority.
3. Map to layout names: left, center, right (first 3 devices).

### Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `MJPEG_PORT` | `8001` | Server listen port |
| `MJPEG_HOST` | `0.0.0.0` | Server bind address |
| `CAMERA_WIDTH` | `640` | Frame width |
| `CAMERA_HEIGHT` | `480` | Frame height |
| `CAMERA_FPS` | `30` | Target framerate |

### Run

```bash
# Standalone
uv run --project server python scripts/mjpeg_debug.py

# Via Makefile
make mjpeg
```

Then open `http://<host>:8001/` in any browser. Each camera renders as an `<img>` tag —
no JavaScript required.

### Lifecycle

- Devices are opened on server startup (not lazy — this is a debug tool, we want
  immediate feedback if a camera fails to initialize).
- Streams run until the server is killed (Ctrl+C).
- Graceful shutdown closes all DepthAI devices.

## Scope

### In scope

- `scripts/mjpeg_debug.py` — standalone server (~100-150 lines)
- `make mjpeg` — Makefile target
- Basic error handling: camera not found, device open failure

### Out of scope (future)

- Integration into gui_api as `/mjpeg/{camera}` endpoint
- React UI toggle between WebRTC and MJPEG
- Recording from MJPEG streams
- Audio

## Tradeoffs vs WebRTC

| | MJPEG (this) | WebRTC (current) |
|---|---|---|
| Complexity | ~100 lines, no deps | MediaMTX + WHEP + ICE + SDP |
| Latency | ~100-200ms | ~50-100ms |
| Bandwidth | Higher (no inter-frame) | Lower (H.264) |
| NAT/firewall | Just HTTP | Needs ICE/STUN/UDP |
| Debug value | High — isolates camera from delivery | N/A |
| USB 2.0 hub (3 cam) | May need to lower FPS to ~15 | Same constraint |

## Implementation steps

1. Create `scripts/mjpeg_debug.py` with device discovery, MJPEG streaming, and index page.
2. Add `make mjpeg` target to Makefile.
3. Test with cameras attached: verify `/cameras` returns names, `/stream/{camera}` renders in browser, `/` shows all three feeds.
4. Add a basic pytest for the `/cameras` endpoint (mock DepthAI devices).
