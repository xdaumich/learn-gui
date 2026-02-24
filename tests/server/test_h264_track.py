"""Tests for telemetry_console.webrtc_track.H264Track."""

import asyncio
import queue as _queue_mod
import time
from unittest.mock import MagicMock

import av

from telemetry_console.webrtc_track import H264Track, VIDEO_TIME_BASE


def _make_feed_queue():
    """Create a controllable mock dai.MessageQueue backed by a thread-safe queue.

    The returned mock has a .feed(data_bytes) method that tests use to inject
    packets one at a time, allowing precise control over timing with the
    background drain thread.
    """
    q = _queue_mod.Queue()
    mock = MagicMock()

    def _try_get():
        try:
            return q.get_nowait()
        except _queue_mod.Empty:
            return None

    mock.tryGet = _try_get

    def _feed(data: bytes):
        pkt = MagicMock()
        pkt.getData.return_value = data
        q.put(pkt)

    mock.feed = _feed
    return mock


# A minimal valid H.264 IDR NAL unit (Annex-B start code + IDR slice header).
_IDR_NAL = b"\x00\x00\x00\x01\x65" + b"\xab" * 20


def _recv_with_timeout(track, timeout=2.0):
    """Run track.recv() with a timeout to avoid hangs in tests."""
    return asyncio.get_event_loop().run_until_complete(
        asyncio.wait_for(track.recv(), timeout=timeout)
    )


def test_recv_returns_av_packet():
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    queue.feed(_IDR_NAL)
    try:
        packet = _recv_with_timeout(track)
        assert isinstance(packet, av.Packet)
    finally:
        track.stop()


def test_recv_first_pts_is_zero():
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    queue.feed(_IDR_NAL)
    try:
        packet = _recv_with_timeout(track)
        assert packet.pts == 0
    finally:
        track.stop()


def test_recv_packet_has_data():
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    queue.feed(_IDR_NAL)
    try:
        packet = _recv_with_timeout(track)
        assert len(bytes(packet)) > 0
    finally:
        track.stop()


def test_recv_second_call_increments_pts():
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    try:
        queue.feed(_IDR_NAL)
        p1 = _recv_with_timeout(track)

        # Small delay to ensure drain thread is ready for next packet.
        time.sleep(0.02)
        queue.feed(_IDR_NAL)
        p2 = _recv_with_timeout(track)

        assert p1.pts == 0
        assert p2.pts == 3000  # 90000 // 30
    finally:
        track.stop()


def test_recv_retries_on_none_without_hanging():
    """tryGet() returning None (empty queue) then a real packet should complete."""
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    try:
        # Don't feed anything yet — drain thread will poll empty queue.
        # After a brief delay, inject the packet.
        asyncio.get_event_loop().call_later(0.05, lambda: queue.feed(_IDR_NAL))
        packet = _recv_with_timeout(track)
        assert isinstance(packet, av.Packet)
        assert packet.pts == 0
    finally:
        track.stop()


def test_recv_skips_empty_payloads():
    """Empty getData() results should be skipped by the drain thread."""
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    try:
        queue.feed(b"")  # empty — should be skipped
        time.sleep(0.02)
        queue.feed(_IDR_NAL)  # real data
        packet = _recv_with_timeout(track)
        assert isinstance(packet, av.Packet)
        assert len(bytes(packet)) > 0
    finally:
        track.stop()


def test_time_base_is_90khz():
    queue = _make_feed_queue()
    track = H264Track(queue=queue, fps=30)
    queue.feed(_IDR_NAL)
    try:
        packet = _recv_with_timeout(track)
        assert packet.time_base == VIDEO_TIME_BASE
    finally:
        track.stop()
