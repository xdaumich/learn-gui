import asyncio
import fractions
import threading

import av
import depthai as dai
from aiortc import MediaStreamTrack

VIDEO_TIME_BASE = fractions.Fraction(1, 90000)  # standard RTP clock for video

# SPS profile bytes that match aiortc's default SDP profile-level-id (42e01f).
# DepthAI's encoder declares a higher level than the actual content needs,
# which causes Chrome to reject the stream.  Patching the SPS to Constrained
# Baseline Level 3.1 keeps Chrome's decoder happy while the actual encoded
# bitstream (640×480 @ 30 fps) is well within Level 3.1 limits.
_SPS_PROFILE_IDC = 0x42       # Baseline
_SPS_CONSTRAINT_FLAGS = 0xE0  # constraint_set0..2 = 1 → Constrained Baseline
_SPS_LEVEL_IDC = 0x1F         # Level 3.1

_NAL_START = b"\x00\x00\x00\x01"

# NAL unit type for IDR (instantaneous decoder refresh) slices.
_NAL_TYPE_IDR = 5


def _patch_sps(data: bytes) -> bytes:
    """Rewrite SPS profile/level bytes so the bitstream matches the SDP.

    Scans *data* for 4-byte Annex-B start codes followed by a SPS NAL
    (type 7).  For each SPS found, the three bytes immediately after the
    NAL header (profile_idc, constraint_set_flags, level_idc) are
    overwritten with values that match aiortc's negotiated
    profile-level-id.  Non-SPS NALs are left untouched.
    """
    buf = bytearray(data)
    i = 0
    patched = False
    while i < len(buf) - 7:
        if buf[i : i + 4] == _NAL_START:
            nal_type = buf[i + 4] & 0x1F
            if nal_type == 7:  # SPS
                buf[i + 5] = _SPS_PROFILE_IDC
                buf[i + 6] = _SPS_CONSTRAINT_FLAGS
                buf[i + 7] = _SPS_LEVEL_IDC
                patched = True
            i += 5
        else:
            i += 1
    return bytes(buf) if patched else data


def _has_idr(data: bytes) -> bool:
    """Return True if *data* contains an IDR slice NAL (type 5)."""
    i = 0
    while i < len(data) - 4:
        if data[i : i + 4] == _NAL_START:
            if data[i + 4] & 0x1F == _NAL_TYPE_IDR:
                return True
            i += 5
        else:
            i += 1
    return False


class H264Track(MediaStreamTrack):
    """aiortc video track that passes DepthAI H.264 NAL bytes directly as av.Packet.

    aiortc's RTCRtpSender detects av.Packet (not av.VideoFrame) and calls
    H264Encoder.pack() instead of encode() — no decode or re-encode happens.

    A background thread continuously drains the DepthAI queue to prevent
    USB XLink buffer overflow when no WebRTC client is connected.

    The last keyframe (IDR) is cached so that ``create_subscriber()`` can
    produce per-peer tracks that always start with a keyframe, regardless
    of when the peer completes ICE negotiation.
    """

    kind = "video"

    def __init__(self, queue: dai.MessageQueue, fps: int) -> None:
        super().__init__()
        self._queue = queue
        self._fps = fps
        self._pts = 0
        self._pts_step = 90000 // max(1, fps)  # pts increment per frame in 90 kHz ticks
        self._latest: bytes | None = None
        self._last_keyframe: bytes | None = None
        # Monotonically increasing sequence number so subscribers can
        # detect when a new frame is available.
        self._seq = 0
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._stop = threading.Event()
        self._drain_thread = threading.Thread(target=self._drain_loop, daemon=True)
        self._drain_thread.start()

    def _drain_loop(self) -> None:
        """Background thread: continuously drain DepthAI queue, keep latest packet.

        Drains ALL available packets in a burst (matching the old
        CameraRelayPublisher behavior) to prevent XLink buffer backup.
        """
        while not self._stop.is_set():
            drained_any = False
            while True:
                try:
                    dai_pkt = self._queue.tryGet()
                except Exception:
                    break
                if dai_pkt is None:
                    break
                drained_any = True
                try:
                    nal_bytes = _patch_sps(bytes(dai_pkt.getData()))
                except Exception:
                    continue
                if nal_bytes:
                    with self._lock:
                        if _has_idr(nal_bytes):
                            self._last_keyframe = nal_bytes
                        self._latest = nal_bytes
                        self._seq += 1
                    self._event.set()
            if not drained_any:
                self._stop.wait(0.001)  # 1ms idle sleep — tight poll

    def create_subscriber(self) -> "H264SubscriberTrack":
        """Create a per-peer track that starts with the cached keyframe."""
        return H264SubscriberTrack(self)

    async def recv(self) -> av.Packet:
        """Receive the latest packet (used by MediaRelay if still wired)."""
        loop = asyncio.get_event_loop()
        while True:
            got_it = await loop.run_in_executor(None, self._event.wait, 0.05)
            if not got_it:
                continue
            self._event.clear()

            nal_bytes = self._latest
            if not nal_bytes:
                continue

            packet = av.Packet(nal_bytes)
            packet.pts = self._pts
            packet.time_base = VIDEO_TIME_BASE
            self._pts += self._pts_step
            return packet

    def stop(self) -> None:
        """Stop the background drain thread and the track."""
        self._stop.set()
        super().stop()


class H264SubscriberTrack(MediaStreamTrack):
    """Per-peer track that reads from a shared H264Track.

    Each subscriber independently tracks which frame it last delivered,
    and always starts with the most recent keyframe so the decoder can
    initialise immediately — even if the subscriber joins mid-stream.
    """

    kind = "video"

    def __init__(self, source: H264Track) -> None:
        super().__init__()
        self._source = source
        self._pts = 0
        self._pts_step = source._pts_step
        self._last_seq = -1
        self._sent_keyframe = False

    async def recv(self) -> av.Packet:
        loop = asyncio.get_event_loop()

        while True:
            got_it = await loop.run_in_executor(
                None, self._source._event.wait, 0.05
            )
            if not got_it:
                continue

            with self._source._lock:
                seq = self._source._seq
                if seq == self._last_seq:
                    continue

                # On first call, start with the cached keyframe so the
                # receiver's decoder can initialise immediately.
                if not self._sent_keyframe:
                    kf = self._source._last_keyframe
                    if kf is not None:
                        nal_bytes = kf
                        self._sent_keyframe = True
                        self._last_seq = seq
                    else:
                        # No keyframe cached yet — wait for one.
                        continue
                else:
                    nal_bytes = self._source._latest
                    self._last_seq = seq

            if not nal_bytes:
                continue

            packet = av.Packet(nal_bytes)
            packet.pts = self._pts
            packet.time_base = VIDEO_TIME_BASE
            self._pts += self._pts_step
            return packet

    def stop(self) -> None:
        super().stop()
