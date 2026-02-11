import depthai as dai
from fastapi.testclient import TestClient

from main import app
import webrtc


def test_webrtc_cameras_endpoint_returns_list(monkeypatch) -> None:
    app.state.recording_manager = None
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_B,
    ]

    monkeypatch.setattr(
        webrtc,
        "ensure_streaming",
        lambda **kwargs: list(kwargs["camera_sockets"]),
    )

    client = TestClient(app)

    response = client.get("/webrtc/cameras")

    assert response.status_code == 200
    assert response.json() == ["CAM_B", "CAM_A"]
