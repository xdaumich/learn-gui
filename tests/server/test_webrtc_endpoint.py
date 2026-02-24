"""Tests for the /webrtc/cameras endpoint."""

from fastapi.testclient import TestClient
import depthai as dai

from main import app
import webrtc


def test_webrtc_cameras_endpoint_orders_provided_sockets(monkeypatch) -> None:
    """Two-camera scenario: socket-fallback path returns ordered names."""
    monkeypatch.setattr(
        "telemetry_console.gui_api._camera_names_from_mediamtx_paths", lambda: None
    )
    app.state.camera_sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_B,
    ]
    client = TestClient(app)

    response = client.get("/webrtc/cameras")
    assert response.status_code == 200
    assert response.json() == ["left", "center"]


def test_webrtc_cameras_endpoint_returns_empty_until_streams_are_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "telemetry_console.gui_api._camera_names_from_mediamtx_paths", lambda: None
    )
    app.state.camera_sockets = None
    monkeypatch.setattr(webrtc, "list_camera_sockets", lambda: [])
    monkeypatch.setattr(webrtc, "list_stream_names", lambda: [])

    client = TestClient(app)
    response = client.get("/webrtc/cameras")

    assert response.status_code == 200
    assert response.json() == []


def test_webrtc_cameras_endpoint_returns_three_streams(monkeypatch) -> None:
    """All three OAK devices should appear as left/center/right."""
    monkeypatch.setattr(
        "telemetry_console.gui_api._camera_names_from_mediamtx_paths", lambda: None
    )
    app.state.camera_sockets = None
    monkeypatch.setattr(webrtc, "list_stream_names", lambda: ["left", "center", "right"])

    client = TestClient(app)
    response = client.get("/webrtc/cameras")

    assert response.status_code == 200
    assert response.json() == ["left", "center", "right"]
