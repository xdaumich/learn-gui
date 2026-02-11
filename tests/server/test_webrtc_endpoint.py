from fastapi.testclient import TestClient
import depthai as dai

from main import app
import webrtc


def test_webrtc_cameras_endpoint_orders_provided_sockets() -> None:
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_B,
    ]
    client = TestClient(app)

    response = client.get("/webrtc/cameras")
    assert response.status_code == 200
    assert response.json() == ["CAM_B", "CAM_A"]


def test_webrtc_cameras_endpoint_falls_back_to_layout(monkeypatch) -> None:
    app.state.camera_sockets = None
    monkeypatch.setattr(webrtc, "list_camera_sockets", lambda: [])

    client = TestClient(app)
    response = client.get("/webrtc/cameras")

    assert response.status_code == 200
    assert response.json()[:3] == ["CAM_B", "CAM_A", "CAM_C"]
