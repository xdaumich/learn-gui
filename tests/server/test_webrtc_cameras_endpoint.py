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
        lambda **_kwargs: app.state.camera_sockets,
    )
    client = TestClient(app)

    response = client.get("/webrtc/cameras")

    assert response.status_code == 200
    assert response.json() == ["CAM_A", "CAM_B"]


def test_webrtc_cameras_endpoint_returns_empty_when_relay_fails(monkeypatch) -> None:
    app.state.recording_manager = None
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
    ]

    def fake_ensure_streaming(**_kwargs):
        raise ValueError("relay init failed")

    monkeypatch.setattr(webrtc, "ensure_streaming", fake_ensure_streaming)
    client = TestClient(app)

    response = client.get("/webrtc/cameras")
    assert response.status_code == 503
    assert response.json()["detail"] == "relay init failed"
