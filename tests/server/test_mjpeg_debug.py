"""Tests for scripts/mjpeg_debug.py MJPEG debug server."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _patch_depthai():
    """Patch depthai before mjpeg_debug is imported so it never touches real hardware."""
    mock_dai = MagicMock()
    mock_dai.Device.getAllAvailableDevices.return_value = []
    with patch.dict(sys.modules, {"depthai": mock_dai}):
        # Remove cached mjpeg_debug so it reimports with mocked depthai
        sys.modules.pop("mjpeg_debug", None)
        yield mock_dai
    sys.modules.pop("mjpeg_debug", None)


def _get_app():
    """Import (or reimport) the mjpeg_debug module and return it."""
    import importlib

    sys.modules.pop("mjpeg_debug", None)
    return importlib.import_module("mjpeg_debug")


def _populate_cameras(mod):
    """Populate module globals as if three cameras were opened."""
    for name in ("left", "center", "right"):
        mod._cameras[name] = name
        mod._devices[name] = MagicMock()
        mod._queues[name] = MagicMock()


# ---------------------------------------------------------------------------
# /cameras endpoint
# ---------------------------------------------------------------------------


def test_cameras_empty_when_no_devices():
    mod = _get_app()
    client = TestClient(mod.app, raise_server_exceptions=False)
    response = client.get("/cameras")
    assert response.status_code == 200
    assert response.json() == []


def test_cameras_returns_layout_names():
    mod = _get_app()
    _populate_cameras(mod)
    client = TestClient(mod.app, raise_server_exceptions=False)
    response = client.get("/cameras")
    assert response.status_code == 200
    assert response.json() == ["left", "center", "right"]


# ---------------------------------------------------------------------------
# / index page
# ---------------------------------------------------------------------------


def test_index_page_no_cameras():
    mod = _get_app()
    client = TestClient(mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    assert "No cameras found" in response.text


def test_index_page_with_cameras():
    mod = _get_app()
    _populate_cameras(mod)
    client = TestClient(mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    for name in ("left", "center", "right"):
        assert name in response.text
        assert f"/stream/{name}" in response.text


# ---------------------------------------------------------------------------
# /stream/{camera}
# ---------------------------------------------------------------------------


def test_stream_404_unknown_camera():
    mod = _get_app()
    client = TestClient(mod.app, raise_server_exceptions=False)
    response = client.get("/stream/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Route existence
# ---------------------------------------------------------------------------


def test_routes_exist():
    mod = _get_app()
    routes = {route.path for route in mod.app.routes}
    assert "/" in routes
    assert "/cameras" in routes
    assert "/stream/{camera}" in routes


# ---------------------------------------------------------------------------
# Device discovery (unit test with mocked depthai)
# ---------------------------------------------------------------------------


def test_discover_cameras_oak_d_center_priority(_patch_depthai):
    """_discover_cameras returns up to 3 DeviceInfo objects."""
    infos = []
    for name in ["OAK-1", "OAK-D-PRO", "OAK-2"]:
        info = MagicMock()
        info.name = name
        info.getMxId.return_value = f"mxid_{name}"
        infos.append(info)
    _patch_depthai.Device.getAllAvailableDevices.return_value = infos

    mod = _get_app()
    result = mod._discover_cameras()
    assert len(result) == 3


def test_discover_cameras_no_devices(_patch_depthai):
    _patch_depthai.Device.getAllAvailableDevices.return_value = []
    mod = _get_app()
    assert mod._discover_cameras() == []
