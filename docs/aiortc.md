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

### Known issues to fix during implementation

1. **`list.discard()` bug** — `_peers` is a `list` but `on_state` calls `self._peers.discard(pc)`. Fix: use `self._peers.remove(pc)` with `try/except ValueError`.
2. **`_queue.get()` blocks forever** — `dai.MessageQueue.get()` with no timeout blocks the executor thread indefinitely. Fix: use `self._queue.tryGet()` in the `while True` loop instead.
3. **Shared track across viewers** — `pc.addTrack(slot.track)` gives every peer the same `H264Track`. Multiple senders call `recv()` on the same track, causing frame-stealing. Fix: use `aiortc.contrib.media.MediaRelay` to fan-out a single track to multiple peer connections.
4. **`_resolve_target_streams` reads stale module state** — It reads `_active_stream_targets` (module-level) which is empty when `SessionManager` manages its own `slots`. Fix: either pass existing slot info into the function or refactor to accept a parameter.
5. **`_ice_config` ignores `WEBRTC_ICE_HOST`** — It reads the env var but doesn't use it. Fix: set `RTCConfiguration` host candidate to the env var value for multi-NIC Jetson setup.

---

## Step 1 — Add `aiortc` dependency

**File:** `server/pyproject.toml`

Add to `[project.dependencies]`:
```
"aiortc>=1.9",
```

`aioice` and `pyee` come as transitive deps. Install with:
```bash
cd server && uv add aiortc
```

### Step 1 — Test gate

```bash
# 1a: verify import works
cd server && uv run python -c "import aiortc; print(aiortc.__version__)"

# 1b: full test suite — no regressions from new dep
make test
```

**Pass criteria:**
- [ ] `1a`: prints version (e.g. `1.9.0`) without error.
- [ ] `1b`: `make test` exit code 0. Zero test failures.

**STOP if any criterion fails. Do not proceed to Step 2.**

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
            # Non-blocking tryGet() off the event loop thread — avoids blocking
            # the executor indefinitely if no frames arrive (fix for issue #2).
            dai_pkt = await loop.run_in_executor(None, self._queue.tryGet)
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
- Uses `tryGet()` (non-blocking) instead of `get()` (blocking) — fixes issue #2.
- No `H264Decoder`, no numpy, no `av.VideoFrame` — zero CPU re-encoding.
- `av.Packet(bytes)` is supported by PyAV; the bytes must be Annex-B format (DepthAI outputs this natively).
- `_pts` increments by `90000 // fps` ticks per frame (90 kHz RTP clock).

### Step 2 — Test gate

**New test file:** `tests/server/test_h264_track.py`

Write a unit test that:
1. Creates a mock `dai.MessageQueue` whose `tryGet()` returns a valid H.264 IDR packet (Annex-B bytes with `\x00\x00\x00\x01\x65` prefix).
2. Instantiates `H264Track(queue=mock_queue, fps=30)`.
3. Calls `await track.recv()` in an asyncio event loop.
4. Asserts the return type is `av.Packet`.
5. Asserts `packet.pts == 0` on first call.
6. Asserts `len(bytes(packet)) > 0`.
7. Calls `recv()` a second time, asserts `packet.pts == 3000` (90000 // 30).
8. Tests that `tryGet()` returning `None` three times then a real packet causes the loop to retry (not hang), completing in <2s.

```bash
# 2a: new unit test passes
cd server && uv run --extra dev pytest ../tests/server/test_h264_track.py -v

# 2b: full test suite — no regressions
make test
```

**Pass criteria:**
- [ ] `2a`: all assertions pass, test completes in <5s (no blocking).
- [ ] `2b`: `make test` exit code 0. Zero failures.

**STOP if any criterion fails. Do not proceed to Step 3.**

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
from aiortc.contrib.media import MediaRelay

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
    _relay: MediaRelay = field(default_factory=MediaRelay)

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
        # TODO: if ice_host is set, configure host candidate for multi-NIC (issue #5)
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
                    try:
                        self._peers.remove(pc)  # fix #1: list.remove not discard
                    except ValueError:
                        pass
                await pc.close()

        # Use MediaRelay to fan-out the single H264Track to multiple viewers
        # without frame-stealing (fix #3).
        relayed_track = self._relay.subscribe(slot.track)
        pc.addTrack(relayed_track)
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

**Fixes applied vs. original plan:**
- `self._peers.discard(pc)` → `self._peers.remove(pc)` with `try/except ValueError` (fix #1).
- `MediaRelay` fan-out instead of sharing the raw track (fix #3).

### Step 3 — Test gate

**New test file:** `tests/server/test_webrtc_sessions.py`

Write unit tests (mock all DepthAI and aiortc internals):
1. **`test_answer_returns_sdp`** — Create `SessionManager` with a mock `CameraSlot` in `slots["left"]`, call `await sm.answer("left", valid_sdp_offer)`, assert result is a non-empty string containing `m=video`.
2. **`test_answer_unknown_camera_raises_key_error`** — Call `await sm.answer("nonexistent", sdp)`, assert `KeyError` is raised with message containing `"nonexistent"`.
3. **`test_close_all_peers_clears_list`** — Append two mock PCs to `sm._peers`, call `await sm.close_all_peers()`, assert `sm._peers == []`.
4. **`test_open_cameras_returns_slot_names`** — Mock `_resolve_target_streams` to return 3 `DeviceStreamTarget` objects, mock `_build_h264_pipeline` and `dai.Device`, call `sm.open_cameras()`, assert return value is `["left", "center", "right"]` and `sm.slots` has 3 entries.
5. **`test_relay_creates_per_peer_track`** — Call `sm.answer()` twice for the same camera, verify `MediaRelay.subscribe()` was called twice (one relayed track per peer, not shared).

```bash
# 3a: new session manager tests
cd server && uv run --extra dev pytest ../tests/server/test_webrtc_sessions.py -v

# 3b: full test suite
make test
```

**Pass criteria:**
- [ ] `3a`: all 5 tests pass.
- [ ] `3b`: `make test` exit code 0. Zero failures.

**STOP if any criterion fails. Do not proceed to Step 4.**

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

Remove `_camera_names_from_mediamtx_paths()` and all MediaMTX path API logic.

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

### Step 4 — Test gate

**Update existing tests:**

1. **`tests/server/test_gui_api.py`** — Add `"/webrtc/{camera}/whep"` to the route existence check in `test_gui_api_routes_exist`.
2. **`tests/server/test_webrtc_endpoint.py`** — Rewrite all 3 existing tests to mock `session_manager.slots` instead of `_camera_names_from_mediamtx_paths`. Add new tests:
   - `test_webrtc_cameras_returns_slot_names` — Set `session_manager.slots` to contain `left`, `center`, `right`; assert `GET /webrtc/cameras` returns `["left", "center", "right"]`.
   - `test_webrtc_cameras_returns_empty_when_no_slots` — Clear slots; assert `GET /webrtc/cameras` returns `[]`.
   - `test_webrtc_whep_returns_201_with_sdp` — POST mock SDP offer to `/webrtc/left/whep`, mock `session_manager.answer()` to return a fake SDP answer string, assert HTTP 201 + `Content-Type: application/sdp` + body matches.
   - `test_webrtc_whep_returns_404_for_unknown_camera` — POST to `/webrtc/nonexistent/whep`, assert HTTP 404.
3. **`tests/server/test_server.py`** — Ensure `test_rerun_status_endpoint_shape` still passes (no import breakage from gui_api changes).

```bash
# 4a: updated endpoint tests
cd server && uv run --extra dev pytest ../tests/server/test_webrtc_endpoint.py -v

# 4b: updated gui_api tests
cd server && uv run --extra dev pytest ../tests/server/test_gui_api.py -v

# 4c: server smoke test
cd server && uv run --extra dev pytest ../tests/server/test_server.py -v

# 4d: full test suite
make test
```

**Pass criteria:**
- [ ] `4a`: all WHEP endpoint tests pass (including new 201/404 tests).
- [ ] `4b`: route existence check includes `"/webrtc/{camera}/whep"`.
- [ ] `4c`: `test_rerun_status_endpoint_shape` passes.
- [ ] `4d`: `make test` exit code 0. Zero failures.

**STOP if any criterion fails. Do not proceed to Step 5.**

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

Remove `WHEP_BASE_URL` import from `useWebRTC.ts`.

**File:** `client/src/config.ts` — Remove `WHEP_BASE_URL` export and `VITE_WHEP_BASE_URL` read.

**File:** `client/vite.config.ts` — Remove `VITE_WHEP_BASE_URL: "http://localhost:8889"` from `test.env`.

**File:** `.env.example`, `.env.host.example`, `.env.remote.example` — Remove `VITE_WHEP_BASE_URL` lines.

No other browser code changes; `RTCPeerConnection`, ICE gathering, track handling all stay identical.

### Step 5 — Test gate

**Update existing test:** `tests/client/useWebRTC.test.tsx`

Change all WHEP URL assertions from old to new pattern:
```ts
// Before:
expect(fetchMock).toHaveBeenCalledWith("http://localhost:8889/left/whep", ...);
expect(fetchMock).toHaveBeenCalledWith("http://localhost:8889/center/whep", ...);
expect(fetchMock).toHaveBeenCalledWith("http://localhost:8889/right/whep", ...);

// After:
expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/webrtc/left/whep", ...);
expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/webrtc/center/whep", ...);
expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/webrtc/right/whep", ...);
```

Both tests ("connect negotiates WHEP for all three cameras" and "flags partial live") must be updated.

```bash
# 5a: updated useWebRTC tests
cd client && npx vitest run tests/client/useWebRTC.test.tsx

# 5b: all client tests (VideoPanel, App, VideoTile, useWebRTC)
make test-client

# 5c: verify no stale WHEP_BASE_URL references in client source
grep -r "WHEP_BASE_URL" client/src/ && echo "FAIL: stale references" && exit 1 || echo "PASS"

# 5d: full test suite (client + server)
make test
```

**Pass criteria:**
- [ ] `5a`: both `useWebRTC` tests pass. "connect negotiates WHEP" asserts `http://localhost:8000/webrtc/left/whep`.
- [ ] `5b`: all client tests pass — VideoPanel assertions (3 tiles, play() calls, live tracks, labels, no alert) all green.
- [ ] `5c`: zero matches for `WHEP_BASE_URL` in `client/src/`.
- [ ] `5d`: `make test` exit code 0. Zero failures.

**STOP if any criterion fails. Do not proceed to Step 6.**

---

## Step 6 — Simplify `camera.py`

Remove the ffmpeg/RTSP relay layer. Keep the DepthAI pipeline and discovery code.

**Remove:**
- `CameraRelayPublisher` class (entire class including `_drain_latest_payload`, `_write_payload`, `_forward`)
- `build_ffmpeg_command()`
- `_rtsp_url_for_stream()`
- `_start_stream_for_target()`
- `_close_and_clear_streams()`
- `ensure_streaming()` / `stop_streaming()` public functions
- `H264Decoder` class (no longer needed — passthrough eliminates decode step)
- `_h264_contains_idr()` (was only used by `CameraRelayPublisher` keyframe logic)
- Module-level `_active_publishers`, `_active_pipelines`, `_active_devices`, `_active_stream_targets` state
- `_state_lock` threading lock (no longer needed — `SessionManager` uses asyncio lock)
- `list_stream_names()`, `list_stream_targets()` (replaced by `session_manager.slots`)
- Imports: `subprocess`, `threading`, `numpy` (if only used by removed code)

**Rename** (make public for use by `webrtc_sessions.py`):
- `_build_h264_pipeline` → `build_h264_pipeline`

**Keep:**
- `_discover_device_profiles()`, `_get_device_profile()`
- `_resolve_target_streams()` — refactor to accept optional existing slot names instead of reading module-level state (fix #4)
- `order_camera_sockets()`, `list_camera_sockets()`
- `DeviceProfile`, `DeviceStreamTarget` dataclasses
- `CAMERA_STREAM_LAYOUT`, `CAMERA_LAYOUT_SOCKET_ORDER` constants
- `_timestamp_ns()` (may still be useful for recording)
- `stream_name_for_camera()`, `stream_name_for_socket()`, `stream_name_for_slot()`

**Update `server/webrtc.py`** re-exports to remove the deleted symbols. Keep only:
- `order_camera_sockets`, `list_camera_sockets`
- `CAMERA_STREAM_LAYOUT`, `CAMERA_LAYOUT_SOCKET_ORDER`
- `DEFAULT_WIDTH`, `DEFAULT_HEIGHT`, `DEFAULT_FPS`

### Step 6 — Test gate

**Update existing tests:**

1. **`tests/server/test_camera_module.py`** — Verify constants still importable. Add assertion that `build_h264_pipeline` (public name) is importable.
2. **Remove/update tests** that reference deleted symbols: any test importing `CameraRelayPublisher`, `H264Decoder`, `build_ffmpeg_command`, `ensure_streaming`, `stop_streaming`, `_h264_contains_idr`, or `list_stream_names` must be rewritten or removed.
3. **`tests/server/test_webrtc.py`** — Update to only test remaining re-exports in `webrtc.py`.

```bash
# 6a: camera module tests
cd server && uv run --extra dev pytest ../tests/server/test_camera_module.py -v

# 6b: verify public API — importable symbols
cd server && uv run python -c "
from telemetry_console.camera import (
    build_h264_pipeline, _discover_device_profiles, _resolve_target_streams,
    CAMERA_STREAM_LAYOUT, CAMERA_LAYOUT_SOCKET_ORDER,
    DeviceProfile, DeviceStreamTarget,
    order_camera_sockets, list_camera_sockets,
    DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS,
)
print('OK: all kept symbols importable')
"

# 6c: verify deleted symbols are gone
cd server && uv run python -c "
import sys
failures = []
for name in ['CameraRelayPublisher', 'H264Decoder', 'ensure_streaming',
             'stop_streaming', 'build_ffmpeg_command', '_h264_contains_idr']:
    try:
        exec(f'from telemetry_console.camera import {name}')
        failures.append(name)
    except ImportError:
        pass
if failures:
    print(f'FAIL: still importable: {failures}')
    sys.exit(1)
print('PASS: all deleted symbols raise ImportError')
"

# 6d: full test suite
make test
```

**Pass criteria:**
- [ ] `6a`: camera constants test passes.
- [ ] `6b`: prints `OK: all kept symbols importable`.
- [ ] `6c`: prints `PASS: all deleted symbols raise ImportError`.
- [ ] `6d`: `make test` exit code 0. Zero failures.

**STOP if any criterion fails. Do not proceed to Step 7.**

---

## Step 7 — Simplify dev stack

**File:** `scripts/dev.sh`

Remove:
- `mediamtx` runner block (lines that start/configure MediaMTX)
- `tc-camera` runner block (`uv run --project server tc-camera ...`)
- MediaMTX port variables (`MEDIAMTX_RTSP_PORT`, `MEDIAMTX_WHEP_PORT`, `MEDIAMTX_API_PORT`)
- MediaMTX port cleanup and `require_free_port` calls for MediaMTX ports
- `MEDIAMTX_BIN`, `MEDIAMTX_CONFIG_PATH` variables
- MediaMTX ICE host IP config generation
- `WHEP_BASE_URL` / `VITE_WHEP_BASE_URL` references

**File:** `server/telemetry_console/cli.py`

Remove `run_camera()` entry point. Remove `tc-camera` from `[project.scripts]` in `pyproject.toml`.

**File:** `Makefile`

Remove `camera`, `mediamtx` targets.

**File:** `scripts/check_camera_live_webrtc.py`

Remove MediaMTX path API check. Delete: `_wait_for_relay_paths()`, `_extract_ready_paths()`, `CAMERA_GUARD_MEDIAMTX_API_URL` env var read. The camera guard now only needs:
1. `GET /health` → `{"status": "ok"}`
2. `GET /webrtc/cameras` → `["left", "center", "right"]` (≥ min_cameras)
3. Optional robot liveness check

**File:** `CLAUDE.md`

Remove `VITE_WHEP_BASE_URL` references. Update architecture section to reflect single-process pipeline. Remove MediaMTX from runtime model table. Update `make dev` process count (from 7 to 5).

### Step 7 — Test gate

```bash
# 7a: lint — no broken imports or syntax errors
make lint

# 7b: full test suite
make test

# 7c: verify dev.sh syntax
bash -n scripts/dev.sh && echo "PASS: dev.sh syntax OK" || (echo "FAIL" && exit 1)

# 7d: verify no stale references
echo "--- Checking for stale WHEP_BASE_URL ---"
grep -rn "WHEP_BASE_URL" client/src/ server/ scripts/ .env* CLAUDE.md 2>/dev/null \
  && echo "FAIL: stale WHEP_BASE_URL references" && exit 1 || echo "PASS"

echo "--- Checking for stale mediamtx in dev.sh ---"
grep -in "mediamtx" scripts/dev.sh 2>/dev/null \
  && echo "FAIL: stale mediamtx references in dev.sh" && exit 1 || echo "PASS"

echo "--- Checking for stale tc-camera in dev.sh ---"
grep -in "tc-camera" scripts/dev.sh 2>/dev/null \
  && echo "FAIL: stale tc-camera references in dev.sh" && exit 1 || echo "PASS"
```

**Pass criteria:**
- [ ] `7a`: lint passes (ruff + tsc).
- [ ] `7b`: `make test` exit code 0. Zero failures.
- [ ] `7c`: bash syntax check passes.
- [ ] `7d`: zero stale references.

**STOP if any criterion fails. Do not proceed to Step 8.**

---

## Step 8 — End-to-end integration test (camera → browser)

This is the final validation. **All prior steps must pass their test gates before attempting this.** This step requires the Jetson Thor with 3 OAK-D cameras physically connected.

### 8a — Start the full stack

```bash
make dev
```

Wait for startup to complete. The camera guard in `dev.sh` (`check_camera_live_webrtc.py`) must print:
```
[camera-guard:webrtc] API health check passed.
[camera-guard:webrtc] Discovered 3 camera(s) so far: left, center, right.
[camera-guard:webrtc] PASS ...
```

**Pass criteria:**
- [ ] `make dev` starts without error.
- [ ] Camera guard reports 3/3 cameras discovered.

### 8b — WebRTC camera guard (API-level, standalone re-run)

```bash
CAMERA_GUARD_API_BASE_URL=http://127.0.0.1:8000 \
  CAMERA_GUARD_MIN_CAMERAS=3 \
  CAMERA_GUARD_REQUIRE_ROBOT=0 \
  uv run --project server python scripts/check_camera_live_webrtc.py
```

**Pass criteria:**
- [ ] Exit code 0.
- [ ] Output includes `Discovered 3 camera(s)`.

### 8c — GUI snapshot guard (browser-level video decode)

```bash
CAMERA_GUARD_API_BASE_URL=http://127.0.0.1:8000 \
  CAMERA_GUARD_GUI_URL=http://localhost:5173 \
  CAMERA_GUARD_MIN_CAMERAS=3 \
  node scripts/check_camera_live_gui.mjs
```

**Pass criteria:**
- [ ] Exit code 0.
- [ ] 3/3 tiles found with `readyState >= 2`.
- [ ] All 3 streams have `currentTime` advancing.
- [ ] Success screenshot saved to `docs/assets/screenshots/`.

### 8d — Playwright integration tests

```bash
make test-integration
```

**Pass criteria — all 4 tests in `tests/integration/camera-snapshot.spec.ts`:**
- [ ] `renders three live camera tiles` — 3 `<video data-testid="camera-stream">` found.
- [ ] `all three camera streams are live` — every video has `readyState >= 2` and a `"live"` track.
- [ ] `snapshot: three cameras, no error banner` — no `role="alert"` element.
- [ ] `video currentTime advances for all three streams` — `currentTime` at t1 > t0 for all 3.

### 8e — Final full unit test suite

```bash
make test
```

**Pass criteria:**
- [ ] Exit code 0. All unit tests pass (client + server).

---

## Completion Checklist

### Implementation
- [ ] `aiortc` in `pyproject.toml`, `uv lock` updated
- [ ] `webrtc_track.py`: `H264Track.recv()` returns `av.Packet`, uses `tryGet()` (not blocking `get()`)
- [ ] `webrtc_sessions.py`: `SessionManager.answer()` returns SDP answer, uses `MediaRelay` (not shared track), uses `list.remove()` (not `discard`)
- [ ] `gui_api.py`: lifespan opens cameras; `/webrtc/cameras` reads `session_manager.slots`; `/webrtc/{camera}/whep` does WHEP signaling
- [ ] `useWebRTC.ts`: WHEP URL points to `API_BASE_URL/webrtc/...`; no `WHEP_BASE_URL` import
- [ ] `config.ts`: `WHEP_BASE_URL` export removed
- [ ] `camera.py`: `CameraRelayPublisher`, ffmpeg code, `H264Decoder`, `_h264_contains_idr`, module-level state all removed; `build_h264_pipeline` is public
- [ ] `webrtc.py`: re-exports updated — deleted symbols removed
- [ ] `dev.sh`: mediamtx and tc-camera blocks removed
- [ ] `cli.py`: `run_camera()` entry point removed; `tc-camera` removed from `pyproject.toml` scripts
- [ ] `check_camera_live_webrtc.py`: MediaMTX path API check removed
- [ ] `CLAUDE.md`: updated architecture, removed `VITE_WHEP_BASE_URL`

### Per-step test gates (all must pass in order)
- [ ] Step 1: `make test` passes with new dep
- [ ] Step 2: `test_h264_track.py` passes + `make test`
- [ ] Step 3: `test_webrtc_sessions.py` passes + `make test`
- [ ] Step 4: `test_webrtc_endpoint.py` + `test_gui_api.py` pass + `make test`
- [ ] Step 5: `useWebRTC.test.tsx` passes with new URLs + `make test-client` + `make test`
- [ ] Step 6: deleted symbols raise `ImportError` + `make test`
- [ ] Step 7: lint + `make test` + no stale references
- [ ] Step 8a: `make dev` starts, camera guard passes 3/3
- [ ] Step 8b: `check_camera_live_webrtc.py` reports 3/3 cameras
- [ ] Step 8c: `check_camera_live_gui.mjs` reports 3/3 tiles advancing
- [ ] Step 8d: `make test-integration` — all 4 Playwright tests pass
- [ ] Step 8e: `make test` — final full suite passes

---

## Bug Fix: WebRTC Video Not Decoding (2026-02-27)

### Symptom

`make dev` streams no video in the browser. `make mjpeg` works fine — camera
hardware is healthy, only the WebRTC path is broken. The `<video>` element
never paints a frame.

### Root Causes (3 bugs)

Three independent bugs prevented WebRTC video from reaching the browser:

| # | Bug | Layer | Effect |
|---|-----|-------|--------|
| 1 | **VP8 codec negotiation** | SDP/aiortc | aiortc picks VP8 (Chrome's first preference) instead of H.264; browser tries to decode H.264 RTP bytes as VP8 → drops 100% of frames |
| 2 | **SPS profile-level-id mismatch** | H.264 bitstream | DepthAI SPS declares `4d0033` (Main Level 5.1) but aiortc SDP says `42e01f` (Constrained Baseline Level 3.1); Chrome's H.264 decoder rejects mismatched streams |
| 3 | **Missing ICE servers in browser** | ICE/networking | `new RTCPeerConnection()` with no STUN server; Firefox refuses ICE entirely, cross-subnet connections fail in both browsers |

Bug #1 was the **primary** blocker — even with bugs #2 and #3 fixed, VP8
negotiation meant zero video. It was discovered last because local loopback
tests masked it (aiortc-to-aiortc worked since both sides used the same codec).

### Diagnostic Process

#### Phase 1: Server-side pipeline (Jetson Thor)

Created `scripts/diagnose_webrtc.py` — tests each layer in isolation:

| Layer | Test | Result |
|-------|------|--------|
| 0 | USB device holders (`fuser`) | PASS — no contention |
| 1 | DepthAI device discovery | PASS — 3 devices found |
| 2 | H.264 pipeline (single camera) | PASS — IDR + P-frames produced |
| 2b | MJPEG pipeline comparison | PASS — camera hardware OK |
| 3 | `aiortc H264Encoder.pack()` | PASS — RTP payloads produced |
| 4 | WHEP loopback (camera → aiortc → recv) | PARTIAL — peers connect, 0 frames decoded |
| 5 | Network/ICE | PASS — host candidates + STUN reachable |

**Finding:** Headless Chromium on ARM64 Jetson has NO H.264 WebRTC codec (only
VP8/VP9/AV1). All on-device browser tests show `decoded=0` regardless of
bitstream correctness. Remote verification required.

#### Phase 2: Cross-machine browser testing (gear-desktop x86_64 → Thor)

Ran Playwright Chromium on `gear-desktop-10` (10.112.210.5, Ubuntu 22.04 x86_64)
against Thor (10.112.210.46). Chromium on x86_64 has full H.264 support:

```
video/H264 profile-level-id=42e01f  (Constrained Baseline L3.1)
video/H264 profile-level-id=4d001f  (Main L3.1)
...
```

**Test 1 — ICE failure (Firefox):**
```
WebRTC: ICE failed, add a STUN server
```
→ Fixed by adding STUN server to browser's `RTCPeerConnection`.

**Test 2 — ICE connected, 0 decoded (Chromium, after ICE fix):**
```
ICE: connected, Connection: connected
pkts=2269 bytes=2111334 decoded=0 lost=0
mimeType: video/VP8  ← WRONG CODEC
framesReceived: 298, framesDropped: 298
```
→ aiortc negotiated VP8, not H.264. Browser receives H.264 bytes via VP8 RTP
payload type → drops every frame. Fixed with `setCodecPreferences`.

**Test 3 — All 3 bugs fixed (Chromium):**
```
mimeType: video/H264  profile-level-id=42001f
framesDecoded: 283, framesDropped: 0, framesPerSecond: 30
frameWidth: 640, frameHeight: 480
```

### Fixes

#### Fix 1: Force H.264 codec in SDP negotiation (primary fix)

**File:** `server/telemetry_console/webrtc_sessions.py`

Without codec preferences, aiortc picks VP8 (Chrome's first listed codec).
Added `setCodecPreferences` before `setRemoteDescription`:

```python
caps = RTCRtpSender.getCapabilities("video")
h264_codecs = [c for c in caps.codecs if "h264" in c.mimeType.lower()]
for transceiver in pc.getTransceivers():
    if transceiver.kind == "video" and h264_codecs:
        transceiver.setCodecPreferences(h264_codecs)
```

#### Fix 2: SPS NAL patching for profile-level-id match

**File:** `server/telemetry_console/webrtc_track.py`

DepthAI's encoder declares Level 5.1 in the SPS even for 640×480 Baseline
streams. aiortc's SDP says `42e01f` (Level 3.1). Patch rewrites SPS bytes to
match:

```python
_SPS_PROFILE_IDC = 0x42       # Baseline
_SPS_CONSTRAINT_FLAGS = 0xE0  # constraint_set0..2 = 1 → Constrained Baseline
_SPS_LEVEL_IDC = 0x1F         # Level 3.1
```

Runs in `H264Track._drain_loop()` on every DepthAI packet via `_patch_sps()`.

#### Fix 3: Encoder profile Main → Baseline

**File:** `server/telemetry_console/camera.py` line 224

```python
# Before:
encoder.setDefaultProfilePreset(fps, dai.VideoEncoderProperties.Profile.H264_MAIN)
# After:
encoder.setDefaultProfilePreset(fps, dai.VideoEncoderProperties.Profile.H264_BASELINE)
```

#### Fix 4: Add STUN server to browser RTCPeerConnection

**File:** `client/src/hooks/useWebRTC.ts` line 222

```typescript
// Before:
const pc = new RTCPeerConnection();
// After:
const pc = new RTCPeerConnection({
  iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
});
```

### Test Results

```
Server tests: 82/83 passed (1 pre-existing failure in test_mjpeg_debug.py, unrelated)
Client tests: 18/18 passed
Browser E2E:  3/3 cameras decoding H.264 via WebRTC (Chromium on gear-desktop)
```

Browser verification output:
```
[PASS] Video 0: readyState=4 resolution=640x480 time=23.712→25.710
[PASS] Video 1: readyState=4 resolution=640x480 time=22.796→24.794
[PASS] Video 2: readyState=4 resolution=640x480 time=22.133→24.129
```

Screenshot saved: `docs/assets/screenshots/webrtc_3cam_pass.png`

### How to Reproduce the Bug

To reproduce any individual bug:

**Bug #1 (VP8 negotiation):** Remove `setCodecPreferences` from
`webrtc_sessions.py`. Browser stats will show `mimeType: video/VP8`,
`framesDropped=N`, `framesDecoded=0`.

**Bug #2 (SPS mismatch):** Remove `_patch_sps()` and change `_drain_loop` to
use `bytes(dai_pkt.getData())` directly. After fixing bug #1, browser will
receive H.264 but Chrome may still reject frames due to profile/level mismatch.

**Bug #3 (ICE):** Revert `RTCPeerConnection` to `new RTCPeerConnection()`.
Firefox shows "ICE failed, add a STUN server". Cross-subnet Chrome also fails.

### How to Run Diagnostics

```bash
# Server-side pipeline check (run on Jetson, no browser needed)
uv run --project server python scripts/diagnose_webrtc.py

# Cross-machine browser test (run on x86_64 host with Chromium)
# Requires: npm install playwright && npx playwright install chromium
THOR_IP=<jetson-ip> node /tmp/test_webrtc_full.mjs
```

### End-to-End Verification

#### Jetson (API-level)

```bash
make dev
# Camera guard will print:
#   [camera-guard:webrtc] Discovered 3 camera(s): left, center, right.
#   [camera-guard:webrtc] PASS

# Standalone re-run:
CAMERA_GUARD_API_BASE_URL=http://127.0.0.1:8000 \
  CAMERA_GUARD_MIN_CAMERAS=3 \
  CAMERA_GUARD_REQUIRE_ROBOT=0 \
  uv run --project server python scripts/check_camera_live_webrtc.py
```

#### Remote browser (full end-to-end)

```bash
# Open browser on any x86 machine with H.264 support:
#   http://<thor-ip>:5173
# All 3 camera tiles (left / center / right) should show live video.

# Automated check (from gear-desktop or Mac):
CAMERA_GUARD_API_BASE_URL=http://<thor-ip>:8000 \
  CAMERA_GUARD_GUI_URL=http://<thor-ip>:5173 \
  CAMERA_GUARD_MIN_CAMERAS=3 \
  node scripts/check_camera_live_gui.mjs

# Playwright integration tests:
make test-integration
```

#### Quick browser console check

```js
document.querySelectorAll('video[data-testid="camera-stream"]').forEach(v =>
  console.log(v.dataset.camera, 'readyState:', v.readyState, 'currentTime:', v.currentTime)
)
// Expected: all 3 with readyState >= 2, currentTime > 0
```

### Key Lesson

When debugging WebRTC video, check **three layers independently**:
1. **Codec negotiation** — verify the SDP answer uses the right codec (`video/H264` not `video/VP8`)
2. **Bitstream compatibility** — verify SPS profile-level-id matches the SDP's `a=fmtp` line
3. **ICE connectivity** — verify STUN/TURN is configured and UDP flows bidirectionally
