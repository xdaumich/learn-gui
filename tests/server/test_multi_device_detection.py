"""Unit tests: three OAK devices detected, assigned left/center/right, API returns all three."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
from typing import Any

import depthai as dai
import pytest
from fastapi.testclient import TestClient

from telemetry_console.camera import (
    CAMERA_STREAM_LAYOUT,
    DeviceProfile,
    DeviceStreamTarget,
    _discover_device_profiles,
    _get_device_profile,
    _resolve_target_streams,
    list_stream_names,
    list_stream_targets,
)

# ---------------------------------------------------------------------------
# Helpers to build fake DeviceInfo objects
# ---------------------------------------------------------------------------

def _fake_device_info(
    *,
    device_id: str = "unknown",
    name: str = "OAK",
) -> dai.DeviceInfo:
    info = MagicMock(spec=dai.DeviceInfo)
    info.deviceId = device_id
    info.name = name
    info.getDeviceId = MagicMock(return_value=device_id)
    return info


def _three_device_infos() -> list[dai.DeviceInfo]:
    return [
        _fake_device_info(device_id="OAK1_LEFT_MXID", name="OAK-1"),
        _fake_device_info(device_id="OAKDW_CENTER_MXID", name="OAK-D-W"),
        _fake_device_info(device_id="OAK1_RIGHT_MXID", name="OAK-1"),
    ]


# ===================================================================
# Test 1: Three devices are discovered from dai.Device
# ===================================================================


class TestThreeDeviceDiscovery:
    """Verify _discover_device_profiles returns profiles for all 3 connected devices."""

    @patch("telemetry_console.camera.dai.Device")
    def test_discovers_three_profiles(self, mock_device_cls: Any) -> None:
        infos = _three_device_infos()
        mock_device_cls.getAllAvailableDevices.return_value = infos

        profiles = _discover_device_profiles()

        assert len(profiles) == 3
        for p in profiles:
            assert isinstance(p, DeviceProfile)

    @patch("telemetry_console.camera.dai.Device")
    def test_identifies_oak_d_model(self, mock_device_cls: Any) -> None:
        infos = _three_device_infos()
        mock_device_cls.getAllAvailableDevices.return_value = infos

        profiles = _discover_device_profiles()

        oak_d_profiles = [p for p in profiles if p.is_oak_d]
        oak_1_profiles = [p for p in profiles if not p.is_oak_d]

        assert len(oak_d_profiles) == 1, "Exactly one OAK-D-W should be detected"
        assert oak_d_profiles[0].device_name == "OAK-D-W"

        assert len(oak_1_profiles) == 2, "Two OAK-1 devices should be detected"
        assert all(p.device_name == "OAK-1" for p in oak_1_profiles)

    @patch("telemetry_console.camera.dai.Device")
    def test_profiles_sorted_oak_d_first(self, mock_device_cls: Any) -> None:
        infos = _three_device_infos()
        mock_device_cls.getAllAvailableDevices.return_value = infos

        profiles = _discover_device_profiles()

        assert profiles[0].is_oak_d, "OAK-D should sort first for center preference"

    @patch("telemetry_console.camera.dai.Device")
    def test_preserves_mxid(self, mock_device_cls: Any) -> None:
        infos = _three_device_infos()
        mock_device_cls.getAllAvailableDevices.return_value = infos

        profiles = _discover_device_profiles()
        device_ids = {p.device_id for p in profiles}

        assert "OAK1_LEFT_MXID" in device_ids
        assert "OAKDW_CENTER_MXID" in device_ids
        assert "OAK1_RIGHT_MXID" in device_ids


# ===================================================================
# Test 2: Three devices are assigned left / center / right
# ===================================================================


class TestThreeDeviceSlotAssignment:
    """Verify _resolve_target_streams assigns positional stream names correctly."""

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_assigns_three_slots(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAKDW_CENTER_MXID", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="OAKDW_CENTER_MXID",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_LEFT_MXID", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_LEFT_MXID",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_RIGHT_MXID", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_RIGHT_MXID",
            ),
        ]

        targets = _resolve_target_streams(requested=None)

        assert len(targets) == 3
        stream_names = [t.stream_name for t in targets]
        assert stream_names == ["left", "center", "right"]

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_oak_d_assigned_to_center(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAKDW", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="OAKDW",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_A", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_A",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_B", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_B",
            ),
        ]

        targets = _resolve_target_streams(requested=None)
        center_target = next(t for t in targets if t.stream_name == "center")

        assert center_target.device_name == "OAK-D-W"

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_oak_1_devices_on_sides(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAKDW", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="OAKDW",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_A", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_A",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_B", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_B",
            ),
        ]

        targets = _resolve_target_streams(requested=None)
        left_target = next(t for t in targets if t.stream_name == "left")
        right_target = next(t for t in targets if t.stream_name == "right")

        assert left_target.device_name == "OAK-1"
        assert right_target.device_name == "OAK-1"

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_each_target_has_distinct_device_id(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAKDW", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="OAKDW",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_A", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_A",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_B", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_B",
            ),
        ]

        targets = _resolve_target_streams(requested=None)
        device_ids = [t.device_id for t in targets]

        assert len(set(device_ids)) == 3, "Each stream target must use a different physical device"

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_stream_names_match_layout_constant(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAKDW", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="OAKDW",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_A", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_A",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1_B", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1_B",
            ),
        ]

        targets = _resolve_target_streams(requested=None)
        stream_names = tuple(t.stream_name for t in targets)

        assert stream_names == CAMERA_STREAM_LAYOUT


# ===================================================================
# Test 3: /webrtc/cameras API returns all three stream names
# ===================================================================


class TestWebRTCCamerasEndpointThreeDevices:
    """Verify the /webrtc/cameras endpoint returns ["left", "center", "right"]."""

    def test_returns_three_stream_names_from_active_targets(self, monkeypatch: Any) -> None:
        """When 3 streams are active, /webrtc/cameras must return all three."""
        import webrtc as webrtc_mod

        monkeypatch.setattr(
            webrtc_mod,
            "list_stream_names",
            lambda: ["left", "center", "right"],
        )

        from main import app

        app.state.camera_sockets = None

        client = TestClient(app)
        response = client.get("/webrtc/cameras")

        assert response.status_code == 200
        cameras = response.json()
        assert cameras == ["left", "center", "right"]
        assert len(cameras) == 3

    def test_returns_three_names_from_mediamtx(self, monkeypatch: Any) -> None:
        """When MediaMTX reports 3 paths, endpoint returns them in layout order."""
        import json
        from io import BytesIO
        from telemetry_console import gui_api

        mediamtx_payload = json.dumps({
            "items": [
                {"name": "right", "ready": True},
                {"name": "left", "ready": True},
                {"name": "center", "ready": True},
            ]
        }).encode()

        def mock_urlopen(url, **kwargs):
            resp = MagicMock()
            resp.read.return_value = mediamtx_payload
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        monkeypatch.setattr(gui_api.urllib_request, "urlopen", mock_urlopen)

        import webrtc as webrtc_mod
        monkeypatch.setattr(
            webrtc_mod,
            "list_stream_names",
            lambda: ["left", "center", "right"],
        )

        from main import app

        client = TestClient(app)
        response = client.get("/webrtc/cameras")

        assert response.status_code == 200
        cameras = response.json()
        assert cameras == ["left", "center", "right"]

    def test_camera_count_is_exactly_three(self, monkeypatch: Any) -> None:
        """Guard test: exactly 3 cameras, not 2 or less."""
        import webrtc as webrtc_mod

        monkeypatch.setattr(
            webrtc_mod,
            "list_stream_names",
            lambda: ["left", "center", "right"],
        )

        from main import app

        app.state.camera_sockets = None

        client = TestClient(app)
        response = client.get("/webrtc/cameras")

        cameras = response.json()
        assert len(cameras) == 3, f"Expected exactly 3 cameras, got {len(cameras)}: {cameras}"


# ===================================================================
# Test 4: DeviceProfile classification
# ===================================================================


class TestDeviceProfileClassification:
    """Verify device model name classification."""

    def test_oak_d_w_is_oak_d(self) -> None:
        profile = DeviceProfile(
            device_info=_fake_device_info(name="OAK-D-W"),
            device_name="OAK-D-W",
            device_id="test",
        )
        assert profile.is_oak_d is True

    def test_oak_d_lite_is_oak_d(self) -> None:
        profile = DeviceProfile(
            device_info=_fake_device_info(name="OAK-D-Lite"),
            device_name="OAK-D-Lite",
            device_id="test",
        )
        assert profile.is_oak_d is True

    def test_oak_1_is_not_oak_d(self) -> None:
        profile = DeviceProfile(
            device_info=_fake_device_info(name="OAK-1"),
            device_name="OAK-1",
            device_id="test",
        )
        assert profile.is_oak_d is False

    def test_get_device_profile_handles_unbooted_usb_name(self) -> None:
        info = _fake_device_info(device_id="MXID_123", name="3.2.1")
        profile = _get_device_profile(info)
        assert profile.device_name == "OAK"
        assert profile.device_id == "MXID_123"

    def test_get_device_profile_recognizes_oak_prefix(self) -> None:
        info = _fake_device_info(device_id="MXID_456", name="OAK-D-W")
        profile = _get_device_profile(info)
        assert profile.device_name == "OAK-D-W"


# ===================================================================
# Test 5: Edge cases
# ===================================================================


class TestEdgeCases:
    """Verify behavior with fewer or more devices."""

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_no_devices_returns_empty(self, mock_discover: Any) -> None:
        mock_discover.return_value = []
        targets = _resolve_target_streams(requested=None)
        assert targets == []

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_one_device_gets_left_slot(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="SOLO", name="OAK-1"),
                device_name="OAK-1",
                device_id="SOLO",
            ),
        ]
        targets = _resolve_target_streams(requested=None)
        assert len(targets) == 1
        assert targets[0].stream_name == "left"

    @patch("telemetry_console.camera._discover_device_profiles")
    def test_two_devices_get_left_center(self, mock_discover: Any) -> None:
        mock_discover.return_value = [
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAKDW", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="OAKDW",
            ),
            DeviceProfile(
                device_info=_fake_device_info(device_id="OAK1", name="OAK-1"),
                device_name="OAK-1",
                device_id="OAK1",
            ),
        ]
        targets = _resolve_target_streams(requested=None)
        assert len(targets) == 2
        names = [t.stream_name for t in targets]
        assert names == ["left", "center"]


# ===================================================================
# Test 6: CameraRelayPublisher.is_healthy()
# ===================================================================

dai = pytest.importorskip("depthai")

from telemetry_console.camera import CameraRelayPublisher  # noqa: E402


class TestCameraRelayPublisherHealthiness:
    """Verify CameraRelayPublisher.is_healthy() logic."""

    def _make_publisher(self) -> CameraRelayPublisher:
        queue = MagicMock(spec=dai.MessageQueue)
        return CameraRelayPublisher(stream_name="test", queue=queue, fps=30)

    def test_thread_never_started(self) -> None:
        publisher = self._make_publisher()
        assert publisher.is_healthy(max_silence_s=5.0) is False

    def test_thread_alive_payload_just_now(self) -> None:
        publisher = self._make_publisher()
        with patch.object(publisher, "is_alive", return_value=True):
            publisher._last_payload_monotonic_s = time.monotonic()
            assert publisher.is_healthy(max_silence_s=5.0) is True

    def test_thread_alive_payload_10s_ago_threshold_5s(self) -> None:
        publisher = self._make_publisher()
        with patch.object(publisher, "is_alive", return_value=True):
            publisher._last_payload_monotonic_s = time.monotonic() - 10
            assert publisher.is_healthy(max_silence_s=5.0) is False

    def test_thread_alive_payload_3s_ago_threshold_5s(self) -> None:
        publisher = self._make_publisher()
        with patch.object(publisher, "is_alive", return_value=True):
            publisher._last_payload_monotonic_s = time.monotonic() - 3
            assert publisher.is_healthy(max_silence_s=5.0) is True

    def test_zero_threshold_clamped(self) -> None:
        publisher = self._make_publisher()
        with patch.object(publisher, "is_alive", return_value=True):
            publisher._last_payload_monotonic_s = time.monotonic()
            assert publisher.is_healthy(max_silence_s=0.0) is True


# ===================================================================
# Test 7: ensure_streaming partial failure
# ===================================================================

from telemetry_console.camera import (  # noqa: E402
    ensure_streaming,
    _start_stream_for_target,
)


class TestEnsureStreamingPartialFailure:
    """Verify ensure_streaming returns only successfully started streams."""

    @patch("telemetry_console.camera._resolve_target_streams")
    @patch("telemetry_console.camera._start_stream_for_target")
    def test_partial_failure_returns_successful_streams(
        self,
        mock_start: Any,
        mock_resolve: Any,
        monkeypatch: Any,
    ) -> None:
        import telemetry_console.camera as cam_mod

        # Isolate global state
        monkeypatch.setattr(cam_mod, "_active_publishers", {})
        monkeypatch.setattr(cam_mod, "_active_pipelines", {})
        monkeypatch.setattr(cam_mod, "_active_devices", {})
        monkeypatch.setattr(cam_mod, "_active_stream_targets", [])

        targets = [
            DeviceStreamTarget(
                device_info=_fake_device_info(device_id="D1", name="OAK-1"),
                device_name="OAK-1",
                device_id="D1",
                stream_name="left",
            ),
            DeviceStreamTarget(
                device_info=_fake_device_info(device_id="D2", name="OAK-D-W"),
                device_name="OAK-D-W",
                device_id="D2",
                stream_name="center",
            ),
            DeviceStreamTarget(
                device_info=_fake_device_info(device_id="D3", name="OAK-1"),
                device_name="OAK-1",
                device_id="D3",
                stream_name="right",
            ),
        ]
        mock_resolve.return_value = targets

        def side_effect(target, **kwargs):
            if target.stream_name == "center":
                raise RuntimeError("center device failed")

        mock_start.side_effect = side_effect

        result = ensure_streaming()
        assert result == ["left", "right"]
