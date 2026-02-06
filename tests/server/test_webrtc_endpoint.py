import asyncio

from aiortc import RTCPeerConnection, VideoStreamTrack
from av import VideoFrame
from fastapi.testclient import TestClient
import depthai as dai

from main import app


class DummyVideoTrack(VideoStreamTrack):
    async def recv(self) -> VideoFrame:
        frame = VideoFrame(width=2, height=2, format="rgb24")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        return frame


def test_webrtc_offer_endpoint_returns_answer() -> None:
    app.state.track_factory = lambda _socket: DummyVideoTrack()
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_B,
    ]

    client = TestClient(app)

    async def run() -> None:
        offerer = RTCPeerConnection()
        for _ in app.state.camera_sockets:
            offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        response = client.post(
            "/webrtc/offer",
            json={"sdp": offerer.localDescription.sdp, "type": offerer.localDescription.type},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["type"] == "answer"
        assert "m=video" in payload["sdp"]

        await offerer.close()
        if hasattr(app.state, "peer_connections"):
            app.state.peer_connections.clear()

    asyncio.run(run())
