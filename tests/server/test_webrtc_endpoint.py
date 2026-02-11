from fastapi.testclient import TestClient
import depthai as dai

from main import app
import webrtc


def test_webrtc_cameras_endpoint_starts_streaming(monkeypatch) -> None:
    app.state.recording_manager = None
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_B,
    ]
    received: dict[str, object] = {}

    def fake_ensure_streaming(*, camera_sockets, recording_manager, **_kwargs):
        received["camera_sockets"] = list(camera_sockets)
        received["recording_manager"] = recording_manager
        return list(camera_sockets)

    monkeypatch.setattr(webrtc, "ensure_streaming", fake_ensure_streaming)
    client = TestClient(app)

    response = client.get("/webrtc/cameras")
    assert response.status_code == 200
    assert response.json() == ["CAM_B", "CAM_A"]

    assert received["camera_sockets"] == [
        dai.CameraBoardSocket.CAM_B,
        dai.CameraBoardSocket.CAM_A,
    ]
    assert received["recording_manager"] is not None
