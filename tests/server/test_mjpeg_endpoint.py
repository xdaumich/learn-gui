"""Tests for /cameras and /stream/{camera} MJPEG endpoints."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import telemetry_console.gui_api as gui_api_module
from telemetry_console.gui_api import app


def test_cameras_returns_slot_names() -> None:
    """All three camera slots populated → returns left/center/right."""
    original = dict(gui_api_module._cameras)
    try:
        gui_api_module._cameras.clear()
        gui_api_module._cameras.update({"left": "left", "center": "center", "right": "right"})

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/cameras")

        assert response.status_code == 200
        assert response.json() == ["left", "center", "right"]
    finally:
        gui_api_module._cameras.clear()
        gui_api_module._cameras.update(original)


def test_cameras_returns_empty_when_no_slots() -> None:
    """No camera slots → returns empty list."""
    original = dict(gui_api_module._cameras)
    try:
        gui_api_module._cameras.clear()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/cameras")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        gui_api_module._cameras.clear()
        gui_api_module._cameras.update(original)


def test_cameras_partial_slots() -> None:
    """Two of three camera slots → returns only populated ones in layout order."""
    original = dict(gui_api_module._cameras)
    try:
        gui_api_module._cameras.clear()
        gui_api_module._cameras.update({"left": "left", "right": "right"})

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/cameras")

        assert response.status_code == 200
        assert response.json() == ["left", "right"]
    finally:
        gui_api_module._cameras.clear()
        gui_api_module._cameras.update(original)


def test_stream_returns_404_for_unknown_camera() -> None:
    """GET /stream/nonexistent → 404."""
    original_queues = dict(gui_api_module._queues)
    try:
        gui_api_module._queues.clear()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/stream/nonexistent")

        assert response.status_code == 404
        assert "nonexistent" in response.text
    finally:
        gui_api_module._queues.clear()
        gui_api_module._queues.update(original_queues)


def test_stream_returns_mjpeg_content_type() -> None:
    """GET /stream/left with a mock queue → multipart/x-mixed-replace."""
    original_queues = dict(gui_api_module._queues)
    original_cameras = dict(gui_api_module._cameras)
    try:
        # Create a mock queue that returns one JPEG frame then raises to stop.
        mock_frame = MagicMock()
        mock_frame.getData.return_value.tobytes.return_value = b"\xff\xd8\xff\xe0fake_jpeg"
        mock_queue = MagicMock()
        call_count = 0

        def get_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_frame
            raise RuntimeError("end of stream")

        mock_queue.get.side_effect = get_side_effect

        gui_api_module._cameras["left"] = "left"
        gui_api_module._queues["left"] = mock_queue

        client = TestClient(app, raise_server_exceptions=False)
        # Use stream=True so we can check headers without reading the full body
        with client.stream("GET", "/stream/left") as response:
            assert response.status_code == 200
            assert "multipart/x-mixed-replace" in response.headers["content-type"]
    finally:
        gui_api_module._queues.clear()
        gui_api_module._queues.update(original_queues)
        gui_api_module._cameras.clear()
        gui_api_module._cameras.update(original_cameras)
