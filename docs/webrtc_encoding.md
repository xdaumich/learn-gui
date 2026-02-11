# WebRTC Encoding Strategy

This document is the **execution plan** for migrating the video pipeline
from host-side software encoding to on-device hardware encoding with a
lightweight media relay.  All encoding happens on the OAK VPU — the host
is relay-only.

## Hardware context

### Cameras (source + encoder)

| Camera | VPU | HW encoder | USB mode |
|---|---|---|---|
| OAK-D W | RVC2 (Myriad X) | H.264, H.265, MJPEG — up to 4K@30 / 1080p@60 | Peripheral only |
| OAK-1 | RVC2 (Myriad X) | H.264, H.265, MJPEG — up to 4K@30 / 1080p@60 | Peripheral only |

Both cameras have a hardware video encoder on the VPU but no
general-purpose CPU.  The standalone `oakctl` mode (device-side WebRTC)
requires RVC4 and is **not available** with this hardware.

### Host (relay-only — no encoding)

| Host | Role | Video HW | Notes |
|---|---|---|---|
| **Jetson Thor** (production) | Relay + recording + Rerun | Dual NVENC (6× 4K@60), dual NVDEC (10× 4K@60) | NVDEC useful for recording decode path |
| **MacBook** (development) | Relay + recording + Rerun | Apple VT (unused) | PyAV software decode is sufficient for dev |

The Jetson Thor has powerful NVENC/NVDEC units and an NVIDIA WebRTC
framework (`NvPassThroughEncoder`), but that framework is C++ only and
Jetson-specific.  Using it would mean maintaining a C++ sidecar and
losing MacBook dev compatibility.  MediaMTX provides the same H.264
passthrough capability as a single cross-platform binary.

### Design constraint

> **All video encoding happens on the OAK device VPU.**
> The host CPU/GPU is never used for encoding.  The host receives
> compressed H.264 NAL units and relays them unmodified to the browser.

---

## Current path (raw frames)

```
OAK ISP → raw RGB888i → USB3 → host Python → aiortc sw encode → WebRTC → browser
                         ↑                         ↑
                   ~180 MB/s @ 1080p30       ~1 CPU core
```

### Pipeline code (`server/webrtc.py`)

```python
cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.RGB888i, fps=fps)
queue   = cam_out.createOutputQueue(blocking=False, maxSize=4)
```

`DepthAIVideoTrack.recv()` pulls a raw numpy array, optionally logs it
to Zarr, wraps it in `av.VideoFrame`, and hands it to aiortc which
software-encodes to VP8/H.264 on the host CPU.

### Cost breakdown

| Resource | Impact |
|---|---|
| USB bandwidth | ~180 MB/s per 1080p30 stream (approaches USB3 ceiling) |
| Host CPU | 1+ core per stream for libvpx / openh264 software encode |
| Latency | ISP → USB transfer → sw encode → RTP packetize → network |
| Multi-camera | Multiplies both bandwidth and CPU linearly |

At 640×480@15 fps (current defaults) the pressure is manageable, but
scaling to 1080p@30 or more cameras will hit the wall fast.

---

## Target path (device H.264 + media relay)

```
OAK ISP → HW H.264 enc → USB3 → host relay → WebRTC → browser
              (VPU)        ↑         ↑
                     ~5 MB/s    near-zero CPU
```

### Architecture diagram

```
┌────────────┐  USB   ┌──────────────────────────────────────────┐  net  ┌─────────┐
│ OAK Device │ ─────→ │ Host (Jetson Thor / MacBook)             │ ────→ │ Browser │
│            │ ~5MB/s │                                          │       │         │
│ ISP → VPU │        │  Python:                                  │       │  WHEP   │
│  H.264 enc│        │    read H.264 NALs from USB               │       │  video  │
│            │        │    pipe to ffmpeg (-c copy)               │       │         │
│            │        │    ffmpeg pushes RTSP to MediaMTX (:8554) │       │         │
│            │        │                                          │       │         │
│            │        │  MediaMTX:                                │       │         │
│            │        │    RTSP in → WHEP out (:8889)            │       │         │
│            │        │                                          │       │         │
│            │        │  FastAPI (:8000):                         │       │         │
│            │        │    Rerun bridge, recording API, health   │       │         │
│            │        │                                          │       │         │
│            │        │  Recording (when active):                 │       │         │
│            │        │    tap H.264 → PyAV/NVDEC decode → Zarr  │       │         │
└────────────┘        └──────────────────────────────────────────┘       └─────────┘
```

---

## Step 1 — Use `dai.node.VideoEncoder` on device

Replace the raw-frame pipeline with the on-VPU hardware encoder.

```python
FPS = 30
KEYFRAME_INTERVAL = 30  # 1 keyframe per second at 30 fps

# request NV12 (native ISP output, no color conversion on device)
cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.NV12, fps=FPS)

# hardware H.264 encoder on the Myriad X VPU
encoder = pipeline.create(dai.node.VideoEncoder)
encoder.setDefaultProfilePreset(FPS, dai.VideoEncoderProperties.Profile.H264_MAIN)
encoder.setKeyframeFrequency(KEYFRAME_INTERVAL)
cam_out.link(encoder.input)

h264_queue = encoder.bitstream.createOutputQueue(blocking=False, maxSize=4)
```

**What changes:**

- USB traffic drops from ~180 MB/s to ~2–8 MB/s per 1080p@30 stream.
- Host receives compressed H.264 NAL units, not raw pixels.
- Encoding CPU usage on the host drops to **zero** (VPU does it).
- The `h264_queue` yields `dai.ImgFrame` packets containing H.264 data
  (Annex B byte stream with SPS/PPS/IDR/slice NALs).
- Keyframe every 30 frames (1 sec) gives good random-access granularity
  for the recording decode path without bloating the bitstream.

**What to verify:**

- `h264_queue.get().getData()` returns bytes starting with a start code
  (`0x00 0x00 0x00 0x01`).
- First packet of each GOP contains SPS + PPS + IDR NAL units.

---

## Step 2 — Install and configure MediaMTX

[MediaMTX](https://github.com/bluenviron/mediamtx) is a single-binary,
zero-dependency media server.  It accepts H.264 via RTSP (among other
protocols) and serves it to browsers via WHEP (WebRTC-HTTP Egress
Protocol).

**Install:**

```bash
# macOS (dev)
brew install mediamtx

# Jetson Thor (production) — download linux-arm64 binary
curl -L https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_v*_linux_arm64v8.tar.gz \
  | tar xz -C /usr/local/bin mediamtx
```

**Default config** (`mediamtx.yml` — only non-default values shown):

```yaml
# Disable protocols we don't use
rtmp: no
hls: no
srt: no

# RTSP: Python pushes H.264 here
rtsp: yes
rtspAddress: :8554

# WebRTC: browser reads WHEP here
webrtc: yes
webrtcAddress: :8889

# Paths are auto-created on first publish
paths:
  all_others:
```

**Verify with a test stream** (before touching DepthAI):

```bash
# terminal 1 — start MediaMTX
mediamtx

# terminal 2 — push a test pattern
ffmpeg -re -f lavfi -i testsrc=size=640x480:rate=30 \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -f rtsp rtsp://localhost:8554/test

# terminal 3 — open in browser
open http://localhost:8889/test
```

**Why MediaMTX:**

- Single static binary — runs on both macOS (dev) and linux-arm64
  (Jetson Thor production) with zero dependencies.
- Native H.264 passthrough — no re-encoding.
- WHEP is a W3C standard — browser client is ~30 lines of JS.
- Built-in MP4 recording if needed as a backup path.
- No GStreamer, no libvpx, no codec dependencies on the host.

### Alternatives considered

| Approach | Effort | Pro | Con |
|---|---|---|---|
| NVIDIA Jetson WebRTC framework (`NvPassThroughEncoder`) | High | Zero-copy on Jetson, native NVIDIA | C++ only, Jetson-specific, no macOS dev |
| aiortc H.264 passthrough | High | No new deps | Requires forking / monkey-patching aiortc internals |
| GStreamer `webrtcbin` | Medium | Mature, native passthrough | Heavy dependency tree, GStreamer pipeline DSL, limited macOS support |
| WHIP/WHEP dedicated server | Medium | Standards-based | MediaMTX already covers this |
| Keep raw frames, lower res | Trivial | No code change | Doesn't solve the fundamental scaling problem |

---

## Step 3 — Python ffmpeg push (H.264 NALs → MediaMTX)

The push layer reads H.264 NAL units from the DepthAI output queue and
pipes them to an `ffmpeg` subprocess that pushes RTSP to MediaMTX.
ffmpeg runs with `-c:v copy` (no transcode) — it only muxes/frames the
raw H.264 byte stream into RTSP.  CPU cost is negligible on either
platform.

```python
import subprocess
import depthai as dai

def start_ffmpeg_rtsp_push(stream_name: str, fps: int = 30) -> subprocess.Popen:
    """Spawn an ffmpeg process that reads raw H.264 from stdin and pushes RTSP."""
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "warning",
        # input: raw H.264 Annex B byte stream from stdin
        "-f", "h264",
        "-framerate", str(fps),
        "-i", "pipe:0",
        # output: RTSP push to MediaMTX, no re-encoding
        "-c:v", "copy",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        f"rtsp://localhost:8554/{stream_name}",
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def stream_camera(h264_queue: dai.DataOutputQueue, stream_name: str, fps: int = 30):
    """Read H.264 packets from DepthAI and write to ffmpeg stdin."""
    proc = start_ffmpeg_rtsp_push(stream_name, fps)
    try:
        while True:
            pkt: dai.ImgFrame = h264_queue.get()
            data = pkt.getData()  # bytes — H.264 Annex B NAL units
            proc.stdin.write(bytes(data))
            proc.stdin.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        proc.stdin.close()
        proc.wait()
```

**Per camera** — spawn one ffmpeg process per camera socket with a
unique stream name (e.g., `cam_a`, `cam_b`).  Each maps to a MediaMTX
path accessible via WHEP at `http://host:8889/cam_a/`, etc.

**What ffmpeg handles for you:**

- Annex B → RTP NAL framing (RFC 6184 packetization)
- SPS/PPS extraction and RTSP DESCRIBE/SETUP negotiation
- Reconnection if MediaMTX restarts
- Timestamp interpolation from frame rate

---

## Step 4 — Replace `useWebRTC.ts` with WHEP client

Remove the custom SDP offer/answer logic and replace it with a WHEP
client that connects directly to MediaMTX.

```typescript
// Minimal WHEP client — one per camera stream
async function connectWHEP(
  streamUrl: string,  // e.g. "http://localhost:8889/cam_a/whep"
  onTrack: (track: MediaStreamTrack) => void,
): Promise<RTCPeerConnection> {
  const pc = new RTCPeerConnection();
  pc.addTransceiver("video", { direction: "recvonly" });

  pc.ontrack = (event) => onTrack(event.track);

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const res = await fetch(streamUrl, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: offer.sdp,
  });
  const answerSdp = await res.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

  return pc;
}
```

**Camera discovery** stays via `GET /webrtc/cameras` on FastAPI.  The
client uses the returned camera names to construct WHEP URLs:

```
GET /webrtc/cameras → ["cam_a", "cam_b"]
→ WHEP connect to http://host:8889/cam_a/whep
→ WHEP connect to http://host:8889/cam_b/whep
```

---

## Step 5 — Recording integration (H.264 → decode on host → Zarr)

Only **one** stream comes over USB per camera: the H.264 bitstream.
No parallel raw queue — this keeps USB bandwidth low even during
recording.

When recording is active, the host taps the same H.264 byte stream,
decodes it to raw RGB frames, and writes to Zarr.

```python
import av

class H264Decoder:
    """Decode H.264 NAL units to raw numpy frames using PyAV."""

    def __init__(self):
        self._codec = av.CodecContext.create("h264", "r")

    def decode(self, nal_data: bytes) -> list:
        """Decode one H.264 access unit, return list of numpy arrays (RGB)."""
        packet = av.Packet(nal_data)
        frames = []
        for frame in self._codec.decode(packet):
            frames.append(frame.to_ndarray(format="rgb24"))
        return frames
```

**Recording flow:**

```
H.264 NALs from DepthAI queue
  ├──→ ffmpeg stdin → MediaMTX → browser  (always)
  └──→ H264Decoder → RGB numpy → Zarr     (only when recording active)
```

**Platform-specific decode:**

| Platform | Decode method | CPU cost |
|---|---|---|
| Jetson Thor | NVDEC hardware decode (via PyAV + `h264_cuvid` or Jetson Multimedia API) | ~0 CPU |
| MacBook | PyAV software decode (`libavcodec`) | ~10% of one core per 1080p@30 stream |

**Keyframe interval** is set to 30 (1 per second at 30 fps).  Since
recording captures all frames via continuous sequential decode, the
keyframe interval has minimal impact — every frame is decoded in order.
If a future change switches to sampled/on-demand recording, the
1-second GOP gives reasonable random-access granularity.

---

## Step 6 — Codebase changes summary

| Component | Current | After migration |
|---|---|---|
| `server/webrtc.py` | `RGB888i` → `DepthAIVideoTrack` → aiortc sw encode | `NV12` → `VideoEncoder` → H.264 pipe to ffmpeg → MediaMTX |
| `server/main.py` | `/webrtc/offer` signaling endpoint | Remove signaling (MediaMTX handles it); keep `/webrtc/cameras` |
| `client/useWebRTC.ts` | Custom SDP offer/answer to FastAPI | WHEP fetch to MediaMTX per-camera endpoints |
| Dependencies | `aiortc` (pulls libvpx, av, ffmpeg bindings) | `ffmpeg` CLI + `mediamtx` binary (external processes) |
| Recording path | Tap raw numpy frames in `DepthAIVideoTrack` | Tap H.264 stream → PyAV decode → Zarr (only when active) |
| Camera discovery | `GET /webrtc/cameras` → transceiver count | Keep as-is; camera names map to MediaMTX stream paths |

---

## Migration checklist

1. [ ] **MediaMTX smoke test** — Install MediaMTX, push a test pattern
       via ffmpeg, open WHEP in browser.  Verify video plays.
       ```bash
       mediamtx &
       ffmpeg -re -f lavfi -i testsrc=640x480:30 -c:v libx264 -preset ultrafast -f rtsp rtsp://localhost:8554/test
       open http://localhost:8889/test
       ```
2. [ ] **Device H.264 encoder** — Add `dai.node.VideoEncoder` to
       `_create_rgb_pipeline` in `server/webrtc.py`.  Confirm H.264
       NALs arrive on host:
       ```python
       pkt = h264_queue.get()
       data = pkt.getData()
       assert data[:4] == b'\x00\x00\x00\x01'  # Annex B start code
       ```
3. [ ] **ffmpeg RTSP push** — Write the Python ffmpeg subprocess push
       (see Step 3 code).  One process per camera.  Verify stream
       appears at `rtsp://localhost:8554/cam_a`.
4. [ ] **WHEP client** — Replace `useWebRTC.ts` SDP logic with WHEP
       client (see Step 4 code).  Connect to MediaMTX per-camera
       endpoints.
5. [ ] **Multi-camera grid** — Verify multi-camera layout still works
       with one WHEP stream per video tile.
6. [ ] **Recording decode path** — Implement `H264Decoder` (see Step 5
       code).  Tap H.264 stream and decode to RGB for Zarr when
       recording is active.  Verify Zarr output matches expected
       frame dimensions and count.
7. [ ] **Remove aiortc** — Delete `aiortc` from `server/pyproject.toml`,
       remove `/webrtc/offer` endpoint, remove `DepthAIVideoTrack`
       class.
8. [ ] **Update docs/infra.md** — Update architecture diagrams to
       reflect the new media path (separate migration step).

---

## Expected gains

| Metric | Before (raw + aiortc) | After (HW enc + MediaMTX) |
|---|---|---|
| USB bandwidth / stream | ~180 MB/s @ 1080p30 | ~5 MB/s @ 1080p30 |
| Host CPU for encoding | ~1 core / stream | ~0 (relay only) |
| Host CPU for recording decode | 0 (raw frames already available) | ~10% core / stream (PyAV); ~0 on Jetson (NVDEC) |
| Max streams before USB bottleneck | 1–2 | 5+ |
| End-to-end latency | ISP → USB xfer → sw encode | ISP → HW encode → USB xfer (smaller payload) |
| Python dependencies | aiortc, av, libvpx | PyAV (decode only), ffmpeg CLI, mediamtx binary |
| Cross-platform | Yes (aiortc runs everywhere) | Yes (ffmpeg + mediamtx have macOS + linux-arm64 builds) |
