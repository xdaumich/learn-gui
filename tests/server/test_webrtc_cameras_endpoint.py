import depthai as dai
from fastapi.testclient import TestClient

from main import app


def test_webrtc_cameras_endpoint_returns_list() -> None:
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_B,
    ]
    client = TestClient(app)

    response = client.get("/webrtc/cameras")

    assert response.status_code == 200
    assert response.json() == ["CAM_A", "CAM_B"]
