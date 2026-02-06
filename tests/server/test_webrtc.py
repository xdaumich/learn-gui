import asyncio

from aiortc import RTCPeerConnection, VideoStreamTrack
from av import VideoFrame

import webrtc


class DummyVideoTrack(VideoStreamTrack):
    async def recv(self) -> VideoFrame:
        frame = VideoFrame(width=2, height=2, format="rgb24")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        return frame


def test_create_answer_negotiates_video() -> None:
    create_answer = getattr(webrtc, "create_answer", None)
    assert create_answer is not None, "create_answer() is missing from webrtc module"

    async def run() -> None:
        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer, pc = await create_answer(
            offerer.localDescription.sdp,
            offerer.localDescription.type,
            track_factory=DummyVideoTrack,
        )

        assert answer.type == "answer"
        assert "m=video" in answer.sdp

        await offerer.close()
        await pc.close()

    asyncio.run(run())
