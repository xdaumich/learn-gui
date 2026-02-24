"""Tests for /webrtc/cameras and /webrtc/{camera}/whep endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from telemetry_console.gui_api import app
from telemetry_console.webrtc_sessions import session_manager, CameraSlot
from telemetry_console.webrtc_track import H264Track


def _make_fake_slot(name: str) -> CameraSlot:
    mock_queue = MagicMock()
    mock_queue.tryGet.return_value = None
    return CameraSlot(
        name=name,
        device=MagicMock(),
        pipeline=MagicMock(),
        track=H264Track(queue=mock_queue, fps=30),
    )


def test_webrtc_cameras_returns_slot_names() -> None:
    """All three camera slots populated → returns left/center/right."""
    original_slots = dict(session_manager.slots)
    try:
        session_manager.slots.clear()
        session_manager.slots["left"] = _make_fake_slot("left")
        session_manager.slots["center"] = _make_fake_slot("center")
        session_manager.slots["right"] = _make_fake_slot("right")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/webrtc/cameras")

        assert response.status_code == 200
        assert response.json() == ["left", "center", "right"]
    finally:
        session_manager.slots.clear()
        session_manager.slots.update(original_slots)


def test_webrtc_cameras_returns_empty_when_no_slots() -> None:
    """No camera slots → returns empty list."""
    original_slots = dict(session_manager.slots)
    try:
        session_manager.slots.clear()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/webrtc/cameras")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        session_manager.slots.clear()
        session_manager.slots.update(original_slots)


def test_webrtc_cameras_partial_slots() -> None:
    """Two of three camera slots → returns only populated ones in layout order."""
    original_slots = dict(session_manager.slots)
    try:
        session_manager.slots.clear()
        session_manager.slots["left"] = _make_fake_slot("left")
        session_manager.slots["right"] = _make_fake_slot("right")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/webrtc/cameras")

        assert response.status_code == 200
        assert response.json() == ["left", "right"]
    finally:
        session_manager.slots.clear()
        session_manager.slots.update(original_slots)


@patch.object(session_manager, "answer", new_callable=AsyncMock)
def test_webrtc_whep_returns_201_with_sdp(mock_answer) -> None:
    """POST valid SDP offer → 201 + application/sdp answer."""
    original_slots = dict(session_manager.slots)
    try:
        session_manager.slots["left"] = _make_fake_slot("left")
        mock_answer.return_value = "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/webrtc/left/whep",
            content="offer-sdp",
            headers={"Content-Type": "application/sdp"},
        )

        assert response.status_code == 201
        assert "application/sdp" in response.headers["content-type"]
        assert "m=video" in response.text
        mock_answer.assert_awaited_once_with("left", "offer-sdp")
    finally:
        session_manager.slots.clear()
        session_manager.slots.update(original_slots)


@patch.object(session_manager, "answer", new_callable=AsyncMock)
def test_webrtc_whep_returns_404_for_unknown_camera(mock_answer) -> None:
    """POST to unknown camera → 404."""
    mock_answer.side_effect = KeyError("nonexistent")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webrtc/nonexistent/whep",
        content="offer-sdp",
        headers={"Content-Type": "application/sdp"},
    )

    assert response.status_code == 404
    assert "nonexistent" in response.text
