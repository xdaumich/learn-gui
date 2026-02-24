"""Tests for telemetry_console.webrtc_track.H264Track."""

import asyncio
from unittest.mock import MagicMock

import av

from telemetry_console.webrtc_track import H264Track, VIDEO_TIME_BASE


def _make_mock_queue(packets):
    """Create a mock dai.MessageQueue whose tryGet() yields from *packets*.

    Each element is either a bytes object (returned as a mock ImgFrame with
    getData()) or None (returned as-is to simulate an empty queue).
    """
    queue = MagicMock()
    items = list(packets)
    idx = {"i": 0}

    def _try_get():
        i = idx["i"]
        if i >= len(items):
            return None
        idx["i"] = i + 1
        item = items[i]
        if item is None:
            return None
        pkt = MagicMock()
        pkt.getData.return_value = item
        return pkt

    queue.tryGet = _try_get
    return queue


# A minimal valid H.264 IDR NAL unit (Annex-B start code + IDR slice header).
_IDR_NAL = b"\x00\x00\x00\x01\x65" + b"\xab" * 20


def test_recv_returns_av_packet():
    queue = _make_mock_queue([_IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    packet = asyncio.get_event_loop().run_until_complete(track.recv())
    assert isinstance(packet, av.Packet)


def test_recv_first_pts_is_zero():
    queue = _make_mock_queue([_IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    packet = asyncio.get_event_loop().run_until_complete(track.recv())
    assert packet.pts == 0


def test_recv_packet_has_data():
    queue = _make_mock_queue([_IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    packet = asyncio.get_event_loop().run_until_complete(track.recv())
    assert len(bytes(packet)) > 0


def test_recv_second_call_increments_pts():
    queue = _make_mock_queue([_IDR_NAL, _IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    loop = asyncio.get_event_loop()
    p1 = loop.run_until_complete(track.recv())
    p2 = loop.run_until_complete(track.recv())
    assert p1.pts == 0
    assert p2.pts == 3000  # 90000 // 30


def test_recv_retries_on_none_without_hanging():
    """tryGet() returning None three times then a real packet should complete quickly."""
    queue = _make_mock_queue([None, None, None, _IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    loop = asyncio.get_event_loop()
    packet = loop.run_until_complete(asyncio.wait_for(track.recv(), timeout=2.0))
    assert isinstance(packet, av.Packet)
    assert packet.pts == 0


def test_recv_skips_empty_payloads():
    """Empty getData() results should be skipped, not returned."""
    queue = _make_mock_queue([b"", _IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    packet = asyncio.get_event_loop().run_until_complete(track.recv())
    assert isinstance(packet, av.Packet)
    assert len(bytes(packet)) > 0


def test_time_base_is_90khz():
    queue = _make_mock_queue([_IDR_NAL])
    track = H264Track(queue=queue, fps=30)
    packet = asyncio.get_event_loop().run_until_complete(track.recv())
    assert packet.time_base == VIDEO_TIME_BASE
