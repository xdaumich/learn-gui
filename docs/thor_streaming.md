# Thor 3-Camera WebRTC Streaming Plan

Stream three OAK cameras from the NVIDIA Jetson Thor to a host computer on the same
LAN, viewed in a browser via WebRTC.

---

## Current State

Everything needed already exists in this codebase. The pipeline is:

```
OAK × 3 (USB)
  │  hardware H.264 encoding (on-VPU)
  ▼
tc-camera (Python, CameraRelayPublisher threads)
  │  ffmpeg -c:v copy  →  RTSP push
  ▼
MediaMTX  (RTSP :8554 → WHEP :8889)
  │  built-in WebRTC gateway
  ▼
Browser  (WHEP client, useWebRTC hook)
  │  RTCPeerConnection per camera
  ▼
VideoPanel  (React grid, <video> elements)
```

### USB devices detected on Thor

| # | VID:PID   | Product          | Serial             | USB Speed |
|---|-----------|------------------|--------------------|-----------|
| 1 | 03e7:f63b | Luxonis Device   | 194430106161DA1700 | 480 Mbps  |
| 2 | 03e7:2485 | Movidius MyriadX | 03e72485           | 480 Mbps  |
| 3 | 03e7:2485 | Movidius MyriadX | 03e72485           | 480 Mbps  |

All three are on Bus 001 via USB 2.0 hubs. Device 1 is already booted
(PID `f63b` = XLink firmware running). Devices 2 and 3 are in unbooted
MyriadX state (PID `2485`) and will boot when DepthAI opens the pipeline.

### Network interfaces on Thor

| Interface | IP              | Notes                    |
|-----------|-----------------|--------------------------|
| mgbe0_0   | 192.168.50.20   | 10 GbE — primary LAN     |
| enP2p1s0  | 192.168.5.20    | secondary Ethernet        |
| wlP1p1s0  | 10.112.210.46   | Wi-Fi (higher latency)    |
| l4tbr0    | 192.168.55.1    | USB device-mode bridge    |
| docker0   | 172.17.0.1      | Docker bridge             |

Pick the interface your host computer shares a subnet with. The example
below assumes **192.168.5.20** (`enP2p1s0`).

---

## Quick Start (two terminals)

### Terminal 1 — on Thor (this machine)

```bash
# One-time setup (installs uv, mediamtx, npm deps)
make setup_remote

# Start MediaMTX + camera relay
make dev_remote
```

This runs `scripts/dev_remote.sh`, which:
1. Cleans stale listeners on ports 8554 / 8889 / 9997.
2. Starts **MediaMTX** with `mediamtx.yml`.
3. Starts **tc-camera** — discovers all OAK sockets, builds a DepthAI H.264
   pipeline, and spawns one `CameraRelayPublisher` thread per camera.
   Each thread pipes H.264 NAL units through ffmpeg into
   `rtsp://127.0.0.1:8554/<socket_name>`.

Camera streams are named after DepthAI sockets: `cam_b` (left), `cam_a`
(center RGB), `cam_c` (right).

### Terminal 2 — on the host PC

```bash
# One-time setup
make setup_host

# Start GUI (Vite + FastAPI + Rerun), pointing WHEP at Thor
THOR_IP=192.168.5.20 make dev_host
```

This runs `scripts/dev_host.sh`, which:
1. Derives `VITE_WHEP_BASE_URL=http://192.168.50.20:8889`.
2. Starts **tc-gui** (FastAPI on :8000, Rerun viewer).
3. Starts **Vite** dev server on :5173.

Open **http://localhost:5173** in a browser. The `VideoPanel` component
calls `GET /webrtc/cameras` (returns `["CAM_B","CAM_A","CAM_C"]`), then
opens one WHEP connection per camera to `http://192.168.50.20:8889/<name>/whep`.

---

## Configuration Reference

### Thor side — `.env.remote` (copy from `.env.remote.example`)

| Variable                 | Default       | Description                          |
|--------------------------|---------------|--------------------------------------|
| `MEDIAMTX_RTSP_PORT`    | 8554          | RTSP ingest port                     |
| `MEDIAMTX_WHEP_PORT`    | 8889          | WHEP (WebRTC) egress port            |
| `MEDIAMTX_API_PORT`     | 9997          | MediaMTX status API                  |
| `WEBRTC_ADDITIONAL_HOSTS` | auto-detect non-loopback IPv4s | Comma-separated ICE host candidates advertised by MediaMTX |
| `CAMERA_WIDTH`           | 640           | Encode width                         |
| `CAMERA_HEIGHT`          | 480           | Encode height                        |
| `CAMERA_FPS`             | 30            | Encode framerate                     |
| `CAMERA_STARTUP_TIMEOUT` | 20.0          | Seconds to wait for cameras to boot  |

### Host side — `.env.host` (copy from `.env.host.example`)

| Variable               | Default                      | Description                      |
|------------------------|------------------------------|----------------------------------|
| `THOR_IP`              | *(required)*                 | Thor's LAN IP                    |
| `VITE_WHEP_BASE_URL`  | `http://<THOR_IP>:8889`     | Auto-derived if THOR_IP is set   |
| `VITE_API_BASE_URL`   | `http://127.0.0.1:8000`     | FastAPI on host                  |
| `HOST_VITE_PORT`       | 5173                         | Vite dev server port             |

---

## Architecture Detail

### DepthAI pipeline (runs on OAK VPU silicon)

```
Camera node  →  NV12 (640×480 @30fps)  →  VideoEncoder (H.264 MAIN)  →  output queue
```

Created in `server/telemetry_console/camera.py::_create_h264_pipeline()`.
One Camera + Encoder pair per detected socket. The encoder produces
Annex-B H.264 NAL units that are read in Python and piped to ffmpeg.

### ffmpeg relay (one subprocess per camera)

```bash
ffmpeg -hide_banner -loglevel warning \
       -fflags +genpts -f h264 -framerate 30 -i pipe:0 \
       -an -c:v copy -f rtsp -rtsp_transport tcp \
       rtsp://127.0.0.1:8554/cam_b
```

Built in `camera.py::build_ffmpeg_command()`. Passthrough only (`-c:v copy`),
no CPU/GPU re-encoding on Thor.

### MediaMTX

Configured via `mediamtx.yml`. Accepts any RTSP publisher on `:8554` and
automatically exposes each stream as a WHEP endpoint on `:8889`.

### Browser WHEP client

`client/src/hooks/useWebRTC.ts` creates an `RTCPeerConnection` per camera,
sends an SDP offer via `POST /<stream>/whep`, receives the answer, and
attaches the resulting `MediaStream` to a `<video>` element in `VideoPanel`.

---

## Firewall / Network Checklist

Open these ports on Thor (or confirm no firewall blocks them):

| Port  | Protocol | Service         | Direction           |
|-------|----------|-----------------|---------------------|
| 8889  | TCP+UDP  | WHEP (WebRTC)   | Host → Thor         |
| 8554  | TCP      | RTSP (internal) | localhost only       |
| 8000  | TCP      | FastAPI (host)  | Host localhost only  |
| 5173  | TCP      | Vite (host)     | Host localhost only  |

WebRTC media flows over UDP. MediaMTX negotiates ICE candidates
automatically; both machines must be on the same L2 subnet (or have
UDP forwarding) for media to flow. If behind NAT, configure a STUN
server in `mediamtx.yml`:

```yaml
webrtcICEServers2:
  - url: stun:stun.l.google.com:19302
```

---

## Troubleshooting

### Only 1–2 cameras appear

The three OAK devices share a USB 2.0 hub chain. USB 2.0 bandwidth
(480 Mbps) is shared across all downstream devices.

- **Lower resolution/fps** — `CAMERA_WIDTH=320 CAMERA_HEIGHT=240 CAMERA_FPS=15 make dev_remote`
- **Check USB topology** — `lsusb -t` and try plugging cameras into
  separate USB root hubs.
- **Check device state** — `lsusb -d 03e7:` should list 3 entries.
  PID `2485` = unbooted MyriadX, PID `f63b` = booted with firmware.

### WHEP connection stuck on "Connecting…"

1. Confirm MediaMTX is running: `curl http://<THOR_IP>:9997/v3/paths/list`
2. Confirm streams are published: each path should show `"ready": true`.
3. On multi-NIC Thor systems, set `WEBRTC_ADDITIONAL_HOSTS` to the host-reachable Thor IP(s), then restart `make dev_remote` (example: `WEBRTC_ADDITIONAL_HOSTS=192.168.5.20 make dev_remote`).
4. Check browser console for ICE failure — may need STUN config (see above).
5. Test RTSP directly: `ffplay rtsp://<THOR_IP>:8554/cam_a`

### High latency

- The pipeline is already zero-copy on the encode path (hardware H.264
  on OAK VPU, passthrough in ffmpeg).
- WebRTC adds ~50–150 ms over LAN. If latency is higher, check
  `mediamtx.yml` — ensure `hls: no` and `rtmp: no` to avoid unnecessary
  transcoding paths.
- Increase keyframe frequency: `--keyframe-interval 15` reduces time-to-first-frame.

### Permission denied on USB

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## Smoke Test Commands

```bash
# Thor — verify cameras are detected
lsusb -d 03e7:
# Should list 3 devices

# Thor — verify MediaMTX paths
curl -s http://127.0.0.1:9997/v3/paths/list | python3 -m json.tool
# Should show cam_a, cam_b, cam_c with "ready": true

# Host — verify WHEP reachability
curl -s -o /dev/null -w "%{http_code}" http://192.168.5.20:8889/cam_a/whep
# Should return 405 (Method Not Allowed for GET; POST is the correct verb)

# Host — verify camera API
curl -s http://127.0.0.1:8000/webrtc/cameras
# Should return ["CAM_B","CAM_A","CAM_C"]

# Host — open browser
open http://localhost:5173    # macOS
xdg-open http://localhost:5173  # Linux
```

---

## Optional Enhancements (future)

| Enhancement                     | Effort | Notes                                              |
|---------------------------------|--------|----------------------------------------------------|
| USB 3.0 passthrough             | Low    | Move cameras to USB 3.x ports for full bandwidth   |
| Per-camera bitrate control      | Medium | Expose encoder bitrate via CLI / API                |
| Dynamic hot-plug                | Medium | Watch `udev` events, restart relay per-camera       |
| TURN relay for remote networks  | Low    | Add TURN server config in `mediamtx.yml`            |
| Recording from host             | Done   | `tc-recorder` already captures H.264 to Zarr        |
| Hardware decode overlay on host | Medium | Use NVDEC on host GPU for low-latency decode        |

---

## File Index

| File | Role |
|------|------|
| `server/telemetry_console/camera.py` | DepthAI pipeline + relay threads |
| `server/telemetry_console/cli.py` | `tc-camera` / `tc-gui` entry points |
| `server/telemetry_console/gui_api.py` | FastAPI `/webrtc/cameras` endpoint |
| `client/src/hooks/useWebRTC.ts` | WHEP client (RTCPeerConnection) |
| `client/src/components/VideoPanel.tsx` | Multi-camera video grid |
| `client/src/config.ts` | `WHEP_BASE_URL`, `API_BASE_URL` |
| `mediamtx.yml` | MediaMTX config (RTSP/WHEP ports) |
| `scripts/dev_remote.sh` | Thor startup script |
| `scripts/dev_host.sh` | Host startup script |
| `.env.remote.example` | Thor env template |
| `.env.host.example` | Host env template |
| `Makefile` | `dev_remote`, `dev_host`, `setup` targets |
