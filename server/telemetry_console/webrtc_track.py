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
