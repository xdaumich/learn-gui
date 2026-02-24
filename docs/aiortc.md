# aiortc Migration Plan

Replace the 3-process WebRTC stack (tc-camera + ffmpeg + MediaMTX) with a single Python process using `aiortc`.

## Pipeline

**Before (3 processes, 8 layers):**
```
OAK-D → DepthAI H.264 → CameraRelayPublisher → ffmpeg stdin → RTSP → MediaMTX → WHEP → RTCPeerConnection → browser
         [tc-camera]                                              [mediamtx]
```

**After (1 process, 4 layers):**
```
OAK-D → DepthAI H.264 → av.Packet → aiortc RTP packetize → DTLS/SRTP → browser
                         [tc-gui: FastAPI + DepthAI + aiortc]
```

**What is removed:** `CameraRelayPublisher`, `ffmpeg` (×3 subprocesses), RTSP, `MediaMTX`, `WHEP_BASE_URL` env var, `tc-camera` CLI entry point, `H264Decoder`, all decode/re-encode CPU cost.

**What is kept:** H.264 on-chip encoding (USB bandwidth unchanged), WebRTC transport (ICE/UDP/DTLS-SRTP), existing `RTCPeerConnection` browser logic.

### Why no decode/re-encode

aiortc's `RTCRtpSender._next_encoded_frame()` checks the return type of `recv()`:

```python
if isinstance(data, Frame):
    payloads, timestamp = encoder.encode(data, force_keyframe)   # encode raw frame
else:
    payloads, timestamp = encoder.pack(data)                      # packetize pre-encoded
```

If `recv()` returns `av.Packet` (not `av.VideoFrame`), aiortc skips encoding entirely and calls `H264Encoder.pack()` — which only extracts NAL units from the Annex-B bitstream and applies FU-A/STAP-A RTP packetization. DepthAI outputs Annex-B H.264 (start codes `\x00\x00\x00\x01`) natively, so the bytes flow straight through.

---

## Step 1 — Add `aiortc` dependency

**File:** `server/pyproject.toml`

Add to `[project.dependencies]`:
```
"aiortc>=1.9",
```

`aioice` and `pyee` come as transitive deps. Verify with:
```bash
cd server && uv add aiortc
```

**Test:** `python -c "import aiortc; print(aiortc.__version__)"` — should print without error.

---

## Step 2 — Create `H264Track`

**New file:** `server/telemetry_console/webrtc_track.py`

```python
import asyncio
import fractions

import av
import depthai as dai
from aiortc import MediaStreamTrack

VIDEO_TIME_BASE = fractions.Fraction(1, 90000)  # standard RTP clock for video


class H264Track(MediaStreamTrack):
    """aiortc video track that passes DepthAI H.264 NAL bytes directly as av.Packet.

    aiortc's RTCRtpSender detects av.Packet (not av.VideoFrame) and calls
    H264Encoder.pack() instead of encode() — no decode or re-encode happens.
    """

    kind = "video"

    def __init__(self, queue: dai.MessageQueue, fps: int) -> None:
        super().__init__()
        self._queue = queue
        self._pts = 0
        self._pts_step = 90000 // max(1, fps)  # pts increment per frame in 90 kHz ticks

    async def recv(self) -> av.Packet:
        loop = asyncio.get_event_loop()

        while True:
            # Blocking queue.get() off the event loop thread.
            dai_pkt = await loop.run_in_executor(None, self._queue.get)
            if dai_pkt is None:
                await asyncio.sleep(0.002)
                continue
            try:
                nal_bytes = bytes(dai_pkt.getData())
            except Exception:
                continue
            if not nal_bytes:
                continue

            # Wrap raw Annex-B H.264 bytes in an av.Packet.
            # aiortc's H264Encoder.pack() will split on start codes and packetize to RTP.
            packet = av.Packet(nal_bytes)
            packet.pts = self._pts
            packet.time_base = VIDEO_TIME_BASE
            self._pts += self._pts_step
            return packet
```

**Notes:**
- No `H264Decoder`, no numpy, no `av.VideoFrame` — zero CPU re-encoding.
- `av.Packet(bytes)` is supported by PyAV; the bytes must be Annex-B format (DepthAI outputs this natively).
- `_pts` increments by `90000 // fps` ticks per frame (90 kHz RTP clock).
- aiortc calls `H264Encoder.pack()` which calls `_split_bitstream()` → NAL unit extraction → FU-A/STAP-A RTP packetization.

**Test:** Instantiate with a mock queue that returns a valid H.264 IDR packet, call `recv()`, assert the returned object is `av.Packet` with `pts == 0` and `len(bytes(packet)) > 0`.

---

## Step 3 — Camera session manager

**New file:** `server/telemetry_console/webrtc_sessions.py`

Holds the per-camera DepthAI state and the per-connection `RTCPeerConnection` objects.

```python
import asyncio
import os
from dataclasses import dataclass, field

import depthai as dai
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from telemetry_console.camera import (
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    DEFAULT_KEYFRAME_INTERVAL,
    _build_h264_pipeline,       # rename to build_h264_pipeline (Step 6)
    _discover_device_profiles,
    _resolve_target_streams,
    CAMERA_STREAM_LAYOUT,
)
from telemetry_console.webrtc_track import H264Track


@dataclass
class CameraSlot:
    name: str          # "left" | "center" | "right"
    device: dai.Device
    pipeline: dai.Pipeline
    track: H264Track


@dataclass
class SessionManager:
    slots: dict[str, CameraSlot] = field(default_factory=dict)
    _peers: list[RTCPeerConnection] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # --- Lifecycle ---

    def open_cameras(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        keyframe_interval: int = DEFAULT_KEYFRAME_INTERVAL,
    ) -> list[str]:
        """Discover and open all available OAK cameras. Returns slot names started."""
        targets = _resolve_target_streams(None)
        for target in targets:
            if target.stream_name in self.slots:
                continue  # already open
            device = dai.Device(target.device_info)
            pipeline, queue = _build_h264_pipeline(
                device=device, width=width, height=height,
                fps=fps, keyframe_interval=keyframe_interval,
            )
            pipeline.start()
            track = H264Track(queue=queue, fps=fps)
            self.slots[target.stream_name] = CameraSlot(
                name=target.stream_name,
                device=device,
                pipeline=pipeline,
                track=track,
            )
        return [s for s in CAMERA_STREAM_LAYOUT if s in self.slots]

    def close_cameras(self) -> None:
        for slot in self.slots.values():
            try:
                slot.pipeline.stop()
            except Exception:
                pass
            try:
                slot.device.close()
            except Exception:
                pass
        self.slots.clear()

    # --- Signaling ---

    def _ice_config(self) -> RTCConfiguration:
        ice_host = os.environ.get("WEBRTC_ICE_HOST", "")
        servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
        return RTCConfiguration(iceServers=servers)

    async def answer(self, camera: str, sdp_offer: str) -> str:
        """Create a WebRTC answer for a WHEP-style SDP offer. Returns SDP answer."""
        slot = self.slots.get(camera)
        if slot is None:
            raise KeyError(f"Camera '{camera}' not available")

        pc = RTCPeerConnection(configuration=self._ice_config())
        async with self._lock:
            self._peers.append(pc)

        @pc.on("connectionstatechange")
        async def on_state():
            if pc.connectionState in ("failed", "closed"):
                async with self._lock:
                    self._peers.discard(pc)
                await pc.close()

        pc.addTrack(slot.track)
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp_offer, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return pc.localDescription.sdp

    async def close_all_peers(self) -> None:
        async with self._lock:
            peers = list(self._peers)
            self._peers.clear()
        for pc in peers:
            await pc.close()


# Module-level singleton used by gui_api.py
session_manager = SessionManager()
```

**Test:** Call `session_manager.answer("left", mock_sdp_offer)` with a valid SDP offer string, assert the returned string contains `a=sendonly` and `m=video`.

---

## Step 4 — FastAPI signaling endpoint

**File:** `server/telemetry_console/gui_api.py`

### 4a — Lifespan: start/stop cameras

Replace the existing lifespan (which called `webrtc.stop_streaming()`):

```python
from telemetry_console.webrtc_sessions import session_manager

@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    session_manager.open_cameras()
    yield
    await session_manager.close_all_peers()
    session_manager.close_cameras()
```

### 4b — `GET /webrtc/cameras`

Replace the MediaMTX path query with a direct read from `session_manager`:

```python
@app.get("/webrtc/cameras")
async def webrtc_cameras() -> list[str]:
    return [s for s in CAMERA_STREAM_LAYOUT if s in session_manager.slots]
```

### 4c — `POST /webrtc/{camera}/whep` (WHEP wire format)

Keep the same URL shape MediaMTX used so browser code only changes the base URL:

```python
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse

@app.post("/webrtc/{camera}/whep")
async def webrtc_whep(camera: str, request: Request) -> Response:
    sdp_offer = (await request.body()).decode()
    try:
        sdp_answer = await session_manager.answer(camera, sdp_offer)
    except KeyError:
        return Response(status_code=404, content=f"Camera '{camera}' not found")
    return PlainTextResponse(sdp_answer, status_code=201, media_type="application/sdp")
```

**Test:** POST a valid SDP offer to `/webrtc/left/whep`, expect HTTP 201 with `Content-Type: application/sdp`.

---

## Step 5 — Update browser signaling URL

**File:** `client/src/hooks/useWebRTC.ts`

Change one function (WHEP URL now points to `API_BASE_URL`, not a separate `WHEP_BASE_URL`):

```ts
// Before:
function whepUrlForCamera(cameraName: string): string {
  return `${WHEP_BASE_URL}/${encodeURIComponent(streamPathForCamera(cameraName))}/whep`;
}

// After:
function whepUrlForCamera(cameraName: string): string {
  return `${API_BASE_URL}/webrtc/${encodeURIComponent(streamPathForCamera(cameraName))}/whep`;
}
```

**File:** `client/src/config.ts` — remove `WHEP_BASE_URL` export and `VITE_WHEP_BASE_URL` read.

**File:** `.env.example`, `.env.host.example`, `.env.remote.example` — remove `VITE_WHEP_BASE_URL` lines.

No other browser code changes; `RTCPeerConnection`, ICE gathering, track handling all stay identical.

---

## Step 6 — Simplify `camera.py`

Remove the ffmpeg/RTSP relay layer. Keep the DepthAI pipeline and decoder code.

**Remove:**
- `CameraRelayPublisher` class (entire class)
- `build_ffmpeg_command()`
- `_rtsp_url_for_stream()`
- `_start_stream_for_target()`
- `_close_and_clear_streams()`
- `ensure_streaming()` / `stop_streaming()` public functions
- `H264Decoder` class (no longer needed — passthrough eliminates decode step)
- `_h264_contains_idr()` (was only used by `CameraRelayPublisher` keyframe logic)
- Module-level `_active_publishers`, `_active_pipelines`, `_active_devices`, `_active_stream_targets` state

**Rename** (make public for use by `webrtc_sessions.py`):
- `_build_h264_pipeline` → `build_h264_pipeline`

**Keep:**
- `_discover_device_profiles()`
- `_resolve_target_streams()`
- `order_camera_sockets()`, `list_camera_sockets()`
- `DeviceProfile`, `DeviceStreamTarget` dataclasses
- `CAMERA_STREAM_LAYOUT`, `CAMERA_LAYOUT_SOCKET_ORDER` constants

**Update `server/webrtc.py`** re-exports to remove the deleted symbols.

---

## Step 7 — Simplify dev stack

**File:** `scripts/dev.sh`

Remove:
- `mediamtx` runner block
- `tc-camera` runner block
- `WHEP_BASE_URL` / `VITE_WHEP_BASE_URL` exports

**File:** `server/telemetry_console/cli.py`

Remove `run_camera()` entry point (cameras now start inside `tc-gui` lifespan). Keep the function stub with a deprecation note or delete it; remove from `[project.scripts]` in `pyproject.toml`.

**File:** `Makefile`

Remove `camera`, `mediamtx` targets from `dev` recipe.

---

## Step 8 — Tests and guard updates

| File | Change |
|------|--------|
| `tests/server/test_server.py` | Replace MediaMTX mock with `session_manager` mock; test `/webrtc/cameras` returns slot names |
| `tests/server/test_webrtc_endpoint.py` | Add test for `POST /webrtc/left/whep` with mock SDP; assert 201 + SDP answer |
| `tests/client/useWebRTC.test.tsx` | Update mock URL from `WHEP_BASE_URL` to `API_BASE_URL/webrtc/...` |
| `scripts/check_camera_live_webrtc.py` | Remove MediaMTX path API check; replace with `GET /webrtc/cameras` check |

**Integration:** `make dev` followed by `node scripts/check_camera_live_gui.mjs` — pass criterion unchanged (3/3 tiles, `currentTime` advancing).

---

## Completion Checklist

- [ ] `aiortc` in `pyproject.toml`, `uv lock` updated
- [ ] `webrtc_track.py`: `H264Track.recv()` returns `av.Packet` with nal_bytes + pts
- [ ] `webrtc_sessions.py`: `session_manager.answer()` returns SDP answer
- [ ] `gui_api.py`: lifespan opens cameras; `/webrtc/cameras` and `/webrtc/{camera}/whep` work
- [ ] `useWebRTC.ts`: WHEP URL points to `API_BASE_URL`; no `WHEP_BASE_URL` reference remains
- [ ] `camera.py`: `CameraRelayPublisher`, ffmpeg code, `H264Decoder`, `_h264_contains_idr` removed
- [ ] `dev.sh`: mediamtx and tc-camera blocks removed
- [ ] `make test` passes
- [ ] `node scripts/check_camera_live_gui.mjs` reports 3/3 advancing
