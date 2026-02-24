import asyncio
import fractions
import threading

import av
import depthai as dai
from aiortc import MediaStreamTrack

VIDEO_TIME_BASE = fractions.Fraction(1, 90000)  # standard RTP clock for video


class H264Track(MediaStreamTrack):
    """aiortc video track that passes DepthAI H.264 NAL bytes directly as av.Packet.

    aiortc's RTCRtpSender detects av.Packet (not av.VideoFrame) and calls
    H264Encoder.pack() instead of encode() — no decode or re-encode happens.

    A background thread continuously drains the DepthAI queue to prevent
    USB XLink buffer overflow when no WebRTC client is connected.
    """

    kind = "video"

    def __init__(self, queue: dai.MessageQueue, fps: int) -> None:
        super().__init__()
        self._queue = queue
        self._pts = 0
        self._pts_step = 90000 // max(1, fps)  # pts increment per frame in 90 kHz ticks
        self._latest: bytes | None = None
        self._event = threading.Event()
        self._stop = threading.Event()
        self._drain_thread = threading.Thread(target=self._drain_loop, daemon=True)
        self._drain_thread.start()

    def _drain_loop(self) -> None:
        """Background thread: continuously drain DepthAI queue, keep latest packet."""
        while not self._stop.is_set():
            try:
                dai_pkt = self._queue.tryGet()
            except Exception:
                self._stop.wait(0.01)
                continue
            if dai_pkt is None:
                self._stop.wait(0.005)
                continue
            try:
                nal_bytes = bytes(dai_pkt.getData())
            except Exception:
                continue
            if nal_bytes:
                self._latest = nal_bytes
                self._event.set()

    async def recv(self) -> av.Packet:
        loop = asyncio.get_event_loop()

        while True:
            # Wait for the drain thread to signal a new packet is available.
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
