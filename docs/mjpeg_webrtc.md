# WebRTC Debugging Plan: MJPEG-first Incremental Verification

## Why MJPEG as the Model

`scripts/mjpeg_debug.py` is the gold standard for camera debugging: standalone, no external services, browser-visible result in seconds. When WebRTC misbehaves it is almost impossible to tell which layer failed (DepthAI? ffmpeg? RTSP? MediaMTX? ICE? SDP? Browser?). This plan applies the same "verify one layer at a time" discipline to the WebRTC stack.

## Pipeline Layers (left to right)

```
[DepthAI H.264 encoder]
       ↓ NAL bytes (queue)
[CameraRelayPublisher thread]
       ↓ stdin pipe
[ffmpeg]
       ↓ RTSP push (TCP)
[MediaMTX :8554]
       ↓ WHEP signaling HTTP
[RTCPeerConnection (browser)]
       ↓ RTP/UDP (ICE)
[<video> element]
```

Each arrow is a potential failure point. The milestones below verify them left-to-right, stopping when one breaks.

---

## Milestone 1 — DepthAI H.264 Encoder Verified

**Goal:** Prove every camera opens, the H.264 pipeline runs, and IDR frames arrive.

**Script:** `scripts/check_h264_frames.py`

Reuse `mjpeg_debug.py`'s `_discover_cameras()` logic but build an H.264 pipeline (matching `camera.py`'s `_build_h264_pipeline`). Read frames from the output queue for 5 s per camera and report:

- Device ID + layout slot assigned
- Frame count received
- Whether an IDR (NAL type 5) + SPS (7) + PPS (8) packet arrived
- First-frame latency in ms

Exit code 0 = all expected cameras produced at least one IDR frame.

**Expected output (3 cameras, healthy):**
```
left   1.2.4.1.1  ✓  42 frames  IDR @212 ms
center 1.2.4.1.2  ✓  40 frames  IDR @198 ms
right  1.2.1.1    ✓  41 frames  IDR @203 ms
PASS  3/3 cameras verified
```

**Run:** `uv run --project server python scripts/check_h264_frames.py`

**What this catches:**
- Device stuck in BOOTED state (only N < 3 cameras found by `getAllAvailableDevices`)
- Encoder producing P-frames before IDR (keyframe ordering bug)
- Wrong slot assignments (OAK-D not landing in `center`)

---

## Milestone 2 — ffmpeg → MediaMTX RTSP Relay Verified

**Goal:** Prove the `CameraRelayPublisher` → ffmpeg → RTSP → MediaMTX path works and streams are visible in MediaMTX's paths API.

**Steps:**
1. Start only MediaMTX and `tc-camera` (no GUI, no browser):
   ```bash
   make mediamtx &
   make camera
   ```
2. Run the existing guard script in standalone mode:
   ```bash
   uv run --project server python scripts/check_camera_live_webrtc.py --min-cameras 3
   ```
3. Probe each RTSP stream with `ffprobe` to confirm H.264 video is decodable:
   ```bash
   ffprobe -v error -show_streams rtsp://127.0.0.1:8554/left 2>&1 | grep codec_name
   ffprobe -v error -show_streams rtsp://127.0.0.1:8554/center 2>&1 | grep codec_name
   ffprobe -v error -show_streams rtsp://127.0.0.1:8554/right 2>&1 | grep codec_name
   ```
4. Query MediaMTX paths API directly:
   ```bash
   curl -s http://127.0.0.1:9997/v3/paths/list | python3 -m json.tool | grep '"name"'
   ```

**Pass criterion:** All 3 paths appear in MediaMTX (`left`, `center`, `right`) and `ffprobe` reports `codec_name: h264`.

**What this catches:**
- ffmpeg exiting immediately (RTSP connection refused, MediaMTX not ready)
- Keyframe issue causing ffmpeg crash loop → empty path in MediaMTX
- Wrong stream name mapping (socket name vs layout name)
- RTSP transport mismatch (TCP vs UDP)

---

## Milestone 3 — WHEP Signaling Verified (No Browser)

**Goal:** Prove the SDP offer → MediaMTX WHEP → SDP answer roundtrip works and ICE candidates appear.

**Script:** `scripts/check_whep.py`

Pure Python using `urllib`. For each camera:
1. Build a minimal SDP offer (video recvonly, H.264)
2. POST to `http://<host>:8889/<camera>/whep`
3. Parse the SDP answer for `a=candidate:` lines and codec
4. Report: HTTP status, round-trip time, ICE candidate count, codec from answer

**Expected output (healthy):**
```
left   200 OK  47 ms  6 ICE candidates  H264
center 200 OK  52 ms  5 ICE candidates  H264
right  200 OK  49 ms  6 ICE candidates  H264
PASS  3/3 WHEP endpoints answered
```

**Run:** `uv run --project server python scripts/check_whep.py --host <thor-ip>`

**What this catches:**
- MediaMTX WHEP endpoint returning 404 (path not published yet)
- ICE candidates contain only localhost (fails on cross-subnet Mac → Thor)
- SDP answer missing H.264 codec (negotiation failure)
- WHEP_BASE_URL misconfigured in client env

---

## Milestone 4 — ICE / UDP Connectivity Verified

**Goal:** Prove RTP packets actually arrive at the client over UDP (the part SSH tunnels break).

**Steps:**

1. Verify `WEBRTC_ICE_HOST` is set to Thor's LAN IP:
   ```bash
   grep WEBRTC_ICE_HOST scripts/dev.sh
   grep WEBRTC_ICE_HOST .env.remote
   ```
2. From the Mac host, run the live check script against Thor's IP:
   ```bash
   node scripts/check_camera_live_gui.mjs
   ```
   This verifies decoded frames are advancing (`currentTime` increases), not just that WHEP connected.

3. If video connects but freezes: capture RTP with `tcpdump` on Thor and `Wireshark` on Mac to confirm UDP packets leave Thor and arrive at Mac.

4. Add `WEBRTC_ICE_HOST` auto-detection to `scripts/dev.sh` (already present — verify it picks up the correct interface IP, not `127.0.0.1`):
   ```bash
   ip route get 8.8.8.8 | awk '{print $7; exit}'
   ```

**Pass criterion:** `check_camera_live_gui.mjs` reports `3/3 tiles readyState ≥ 2 AND currentTime advancing`.

**What this catches:**
- ICE host IP is loopback → RTP goes nowhere on remote Mac
- UDP blocked by firewall (only TCP SSH tunnel in use)
- Tailscale/WireGuard needed but not active
- One camera stream stalls while others advance (per-stream ICE failure)

---

## Milestone 5 — Integrated Diagnostic Page

**Goal:** Add a built-in `/debug` HTML page to `tc-gui` (FastAPI) that shows all pipeline layers at a glance — like `mjpeg_debug.py`'s index page, but for WebRTC health.

**New endpoint:** `GET /debug` on the FastAPI server (`:8000`)

Page sections:
1. **Camera Discovery** — lists devices returned by `getAllAvailableDevices()` (calls `list_stream_names()`)
2. **MediaMTX Paths** — live call to `9997/v3/paths/list`; green/red per stream
3. **WHEP Endpoints** — server-side WHEP probe for each camera (HTTP status + latency)
4. **MJPEG Fallback Preview** — embeds MJPEG streams via `<img>` tags (reuse `mjpeg_debug.py` logic, runs in-process or sidecar) so you can visually confirm cameras produce frames even when WebRTC is broken
5. **Client Env** — echoes `VITE_API_BASE_URL`, `VITE_WHEP_BASE_URL`, `WEBRTC_ICE_HOST` for quick misconfiguration detection

**Implementation notes:**
- Add `GET /debug` to `gui_api.py` returning `HTMLResponse`
- MJPEG fallback uses a separate FastAPI router mounted at `/mjpeg/stream/{camera}` — reuse `_build_mjpeg_pipeline` from `mjpeg_debug.py`
- Auto-refresh every 3 s via `<meta http-equiv="refresh">`

**Run:** Open `http://<thor-ip>:8000/debug` in any browser

**Pass criterion:** Page loads, shows 3/3 cameras green for MediaMTX paths and WHEP, and MJPEG thumbnails display live frames.

---

## Test Commands Summary

| Milestone | Command | Expected |
|-----------|---------|---------|
| M1 — H.264 encoder | `uv run --project server python scripts/check_h264_frames.py` | `3/3 PASS` |
| M2 — RTSP relay | `make mediamtx && make camera && ffprobe rtsp://127.0.0.1:8554/left` | `codec_name: h264` × 3 |
| M2 — MediaMTX paths | `curl http://127.0.0.1:9997/v3/paths/list` | `left`, `center`, `right` present |
| M3 — WHEP signaling | `uv run --project server python scripts/check_whep.py` | `3/3 PASS` |
| M4 — UDP frames | `node scripts/check_camera_live_gui.mjs` | `3/3 advancing` |
| M5 — Visual check | Browser → `http://<thor>:8000/debug` | All green + MJPEG visible |

## Failure Triage Matrix

| Symptom | Likely layer | First check |
|---------|-------------|-------------|
| `check_h264_frames.py` shows < 3 cameras | DepthAI / USB | Device BOOTED state; unplug/replug |
| No IDR in first 5 s | Encoder | Keyframe interval setting; `_needs_keyframe` flag |
| ffprobe to RTSP times out | ffmpeg → MediaMTX | ffmpeg process alive? RTSP port 8554 open? |
| MediaMTX paths shows path but no publisher | CameraRelayPublisher | ffmpeg stdin pipe error; `EPIPE` in camera logs |
| WHEP returns 404 | MediaMTX path not published | Wait for M2 to pass first |
| WHEP returns ICE candidates but video freezes | ICE / UDP | `WEBRTC_ICE_HOST` set to routable IP? |
| Tiles show in browser but stall after ~15 s | Stall detector + stream health | Check `is_healthy()` watchdog; RTSP path drops |
| Only 1–2 cameras in browser | Partial relay startup | Right camera BOOTED; `--min-cameras 3` retry loop |
