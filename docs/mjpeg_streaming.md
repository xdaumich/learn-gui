# MJPEG Debug Streaming

Standalone MJPEG server for debugging camera connectivity without WebRTC/MediaMTX.

## Motivation

The WebRTC pipeline (DepthAI → FFmpeg → MediaMTX RTSP → WHEP → browser) has many
failure points: ICE negotiation, SDP exchange, UDP port allocation, MediaMTX config,
H.264 codec support. When video doesn't appear, it's hard to tell if the problem is
the camera or the delivery layer.

MJPEG over HTTP eliminates all of that. If MJPEG works but WebRTC doesn't, the
cameras are fine and the problem is in the relay/signaling stack.

## Two-machine workflow

| Machine | Role | What runs |
|---------|------|-----------|
| **Jetson Thor** | Streams cameras | `make mjpeg` (FastAPI + DepthAI on `:8001`) |
| **Mac host** | Views + saves | Browser at `http://$THOR_IP:8001/`, curl/ffmpeg for saving |

```
Thor (OAK cameras)                         Mac host
┌────────────────────────┐                ┌──────────────────────────┐
│  scripts/mjpeg_debug.py │               │                          │
│                         │  HTTP :8001   │  Browser → view streams  │
│  OAK-D → MJPEG encoder │ ───────────── │  curl    → save snapshot │
│  → FastAPI server       │               │  ffmpeg  → record MP4    │
└────────────────────────┘                └──────────────────────────┘
```

No SSH tunnel needed — plain HTTP works over any network path (LAN, Tailscale, etc.).

### Thor network binding

The server must bind to an interface reachable by the Mac host (typically WiFi).
Set `THOR_IP` in your `.env.host` (or `.env.remote`) to the WiFi address:

```bash
# .env.remote (Thor side)
MJPEG_HOST=0.0.0.0       # bind all interfaces (default, works out of the box)
MJPEG_PORT=8001

# .env.host (Mac side)
THOR_IP=10.112.210.46     # Thor's WiFi IP (wlP1p1s0)
```

Find Thor's WiFi IP:
```bash
ip -4 addr show wlP1p1s0 | grep -oP 'inet \K[0-9.]+'
```

Verify from the Mac host:
```bash
curl http://$THOR_IP:8001/cameras
# Expected: ["left","center","right"]
```

## Design

### What

`scripts/mjpeg_debug.py` — a self-contained FastAPI server that streams MJPEG from
connected OAK cameras over plain HTTP. No dependency on tc-camera, MediaMTX, tc-gui,
or any other service.

### Minimal dependencies

Only two Python packages beyond stdlib:

| Package | Purpose |
|---------|---------|
| `depthai` | OAK camera access + on-device MJPEG encoding |
| `fastapi` + `uvicorn` | HTTP server |

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

## Start streaming (Thor)

```bash
# Via Makefile
make mjpeg

# Or directly
uv run --project server python scripts/mjpeg_debug.py
```

Devices are opened on server startup (not lazy — immediate feedback if a camera
fails to initialize). Streams run until Ctrl+C. Graceful shutdown closes all
DepthAI devices.

## View in browser (host)

Open `http://$THOR_IP:8001/` in any browser. Each camera renders as an `<img>` tag —
no JavaScript required.

Individual streams are at `http://$THOR_IP:8001/stream/{camera}` where camera is
`left`, `center`, or `right`.

Check available cameras: `curl http://$THOR_IP:8001/cameras`

## Save image/video (host)

All saving happens on the host machine. `scripts/save_mjpeg.py` connects to Thor's
MJPEG server over HTTP and saves JPEG snapshots or MP4 video using OpenCV.

### Prerequisites (Mac host)

```bash
pip install opencv-python    # or: pip install opencv-python-headless
```

### Python script: `scripts/save_mjpeg.py`

```bash
# Snapshot all cameras (saves to ./captures/<camera>_<timestamp>.jpg)
python scripts/save_mjpeg.py --host $THOR_IP snapshot

# Snapshot one camera
python scripts/save_mjpeg.py --host $THOR_IP --camera center snapshot

# Record 10s MP4 from all cameras (saves to ./captures/<camera>_<timestamp>.mp4)
python scripts/save_mjpeg.py --host $THOR_IP record --duration 10

# Record center only, custom output dir
python scripts/save_mjpeg.py --host $THOR_IP --camera center --out ./my_clips record --duration 30
```

The script auto-discovers cameras via `GET /cameras`, reads the MJPEG stream with
`cv2.VideoCapture`, and writes MP4 with `cv2.VideoWriter`. No ffmpeg binary needed.

### Quick reference

| Task | Command |
|------|---------|
| List cameras | `curl http://$THOR_IP:8001/cameras` |
| Snapshot all | `python scripts/save_mjpeg.py --host $THOR_IP snapshot` |
| Snapshot one | `python scripts/save_mjpeg.py --host $THOR_IP --camera center snapshot` |
| Record 10s all | `python scripts/save_mjpeg.py --host $THOR_IP record --duration 10` |
| Record one | `python scripts/save_mjpeg.py --host $THOR_IP --camera center record --duration 10` |

## Tradeoffs vs WebRTC

| | MJPEG (this) | WebRTC (current) |
|---|---|---|
| Complexity | ~300 lines, 2 deps | MediaMTX + WHEP + ICE + SDP |
| Latency | ~100-200ms | ~50-100ms |
| Bandwidth | Higher (no inter-frame) | Lower (H.264) |
| NAT/firewall | Just HTTP | Needs ICE/STUN/UDP |
| Save to disk | curl/ffmpeg against HTTP | Requires browser MediaRecorder or server-side |
| Debug value | High — isolates camera from delivery | N/A |
| USB 2.0 hub (3 cam) | May need to lower FPS to ~15 | Same constraint |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No cameras found" on `/` | No OAK devices detected | Check USB connections, run `lsusb` on Thor |
| Port 8001 already in use | Previous instance still running | Script auto-kills stale process; or `fuser -k 8001/tcp` |
| ffmpeg hangs on connect | Thor firewall blocking port | Check `ufw status` on Thor, allow 8001 |
| Choppy stream (3 cameras) | USB 2.0 bandwidth limit | Lower FPS: `CAMERA_FPS=15 make mjpeg` |
| Black frames | Camera needs warmup | Wait 1-2 seconds after startup |
