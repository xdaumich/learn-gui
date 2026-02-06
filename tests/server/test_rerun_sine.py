"""Tests for the Rerun bridge sine-wave streaming."""

from __future__ import annotations

import threading
import time
import urllib.request

import pytest


def test_rerun_bridge_start_and_stream():
    """Start the bridge, stream a few data points, and verify the web viewer is reachable."""
    import rerun_bridge

    # Use non-default ports to avoid clashes with a running dev session
    grpc_port = 19876
    web_port = 19090

    url = rerun_bridge.start(grpc_port=grpc_port, web_port=web_port, open_browser=False)
    assert url == f"http://localhost:{web_port}"
    assert rerun_bridge.is_running()
    assert rerun_bridge.web_url() == url

    # Stream for a short burst in a background thread
    t = threading.Thread(
        target=rerun_bridge.stream_sine_wave,
        kwargs={"hz": 20, "duration": 1.5},
        daemon=True,
    )
    t.start()

    # Give the web viewer a moment to bind
    time.sleep(1.0)

    # Verify the HTTP web viewer responds
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        assert resp.status == 200
    except Exception as exc:
        pytest.fail(f"Web viewer not reachable at {url}: {exc}")

    t.join(timeout=5)
