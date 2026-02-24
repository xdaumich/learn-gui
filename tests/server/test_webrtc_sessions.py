"""Tests for telemetry_console.webrtc_sessions.SessionManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telemetry_console.webrtc_sessions import SessionManager, CameraSlot
from telemetry_console.webrtc_track import H264Track


def _make_fake_slot(name: str) -> CameraSlot:
    """Create a CameraSlot with mock internals for testing."""
    mock_queue = MagicMock()
    mock_queue.tryGet.return_value = None
    return CameraSlot(
        name=name,
        device=MagicMock(),
        pipeline=MagicMock(),
        track=H264Track(queue=mock_queue, fps=30),
    )


# A minimal SDP offer that aiortc can parse (video m-line required).
_MINIMAL_SDP_OFFER = (
    "v=0\r\n"
    "o=- 0 0 IN IP4 127.0.0.1\r\n"
    "s=-\r\n"
    "t=0 0\r\n"
    "m=video 9 UDP/TLS/RTP/SAVPF 96\r\n"
    "c=IN IP4 0.0.0.0\r\n"
    "a=mid:0\r\n"
    "a=recvonly\r\n"
    "a=rtpmap:96 H264/90000\r\n"
    "a=fmtp:96 profile-level-id=42e01f;level-asymmetry-allowed=1;packetization-mode=1\r\n"
    "a=rtcp-mux\r\n"
    "a=setup:actpass\r\n"
    "a=ice-ufrag:test\r\n"
    "a=ice-pwd:testpasswordtestpassword\r\n"
    "a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:"
    "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00\r\n"
)


def test_answer_returns_sdp():
    sm = SessionManager()
    sm.slots["left"] = _make_fake_slot("left")

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(sm.answer("left", _MINIMAL_SDP_OFFER))

    assert isinstance(result, str)
    assert len(result) > 0
    assert "m=video" in result

    # Clean up peers
    loop.run_until_complete(sm.close_all_peers())


def test_answer_unknown_camera_raises_key_error():
    sm = SessionManager()

    with pytest.raises(KeyError, match="nonexistent"):
        asyncio.get_event_loop().run_until_complete(
            sm.answer("nonexistent", _MINIMAL_SDP_OFFER)
        )


def test_close_all_peers_clears_list():
    sm = SessionManager()
    mock_pc1 = MagicMock()
    mock_pc1.close = AsyncMock()
    mock_pc2 = MagicMock()
    mock_pc2.close = AsyncMock()
    sm._peers = [mock_pc1, mock_pc2]

    asyncio.get_event_loop().run_until_complete(sm.close_all_peers())

    assert sm._peers == []
    mock_pc1.close.assert_awaited_once()
    mock_pc2.close.assert_awaited_once()


@patch("telemetry_console.webrtc_sessions._resolve_target_streams")
@patch("telemetry_console.webrtc_sessions.dai.Device")
@patch("telemetry_console.webrtc_sessions._build_h264_pipeline")
def test_open_cameras_returns_slot_names(mock_build, mock_device_cls, mock_resolve):
    from telemetry_console.camera import DeviceStreamTarget

    mock_resolve.return_value = [
        DeviceStreamTarget(stream_name="left", device_info=MagicMock(), device_name="OAK", device_id="d1"),
        DeviceStreamTarget(stream_name="center", device_info=MagicMock(), device_name="OAK-D", device_id="d2"),
        DeviceStreamTarget(stream_name="right", device_info=MagicMock(), device_name="OAK", device_id="d3"),
    ]
    mock_device_cls.return_value = MagicMock()
    mock_pipeline = MagicMock()
    mock_queue = MagicMock()
    mock_queue.tryGet.return_value = None
    mock_build.return_value = (mock_pipeline, mock_queue)

    sm = SessionManager()
    result = sm.open_cameras()

    assert result == ["left", "center", "right"]
    assert set(sm.slots.keys()) == {"left", "center", "right"}


def test_relay_creates_per_peer_track():
    sm = SessionManager()
    sm.slots["left"] = _make_fake_slot("left")

    loop = asyncio.get_event_loop()

    # Call answer twice for the same camera
    loop.run_until_complete(sm.answer("left", _MINIMAL_SDP_OFFER))
    loop.run_until_complete(sm.answer("left", _MINIMAL_SDP_OFFER))

    # Each answer() should have created a separate relayed track via MediaRelay.subscribe()
    # Verify we have 2 peers (one per answer call)
    assert len(sm._peers) == 2

    # Clean up
    loop.run_until_complete(sm.close_all_peers())
