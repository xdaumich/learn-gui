import asyncio

from aiortc import RTCPeerConnection, VideoStreamTrack
from av import VideoFrame

import depthai as dai

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
        camera_sockets = [
            dai.CameraBoardSocket.CAM_A,
            dai.CameraBoardSocket.CAM_B,
        ]
        offerer = RTCPeerConnection()
        for _ in camera_sockets:
            offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)
        answer, pc = await create_answer(
            offerer.localDescription.sdp,
            offerer.localDescription.type,
            camera_sockets=camera_sockets,
            track_factory=lambda _socket: DummyVideoTrack(),
        )

        assert answer.type == "answer"
        video_transceivers = [t for t in pc.getTransceivers() if t.kind == "video"]
        assert len(video_transceivers) == len(camera_sockets)

        await offerer.close()
        await pc.close()

    asyncio.run(run())
