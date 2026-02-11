"""Backward-compat shim for webrtc module."""

import av  # noqa: F401

from telemetry_console.camera import (  # noqa: F401
    ensure_streaming as _ensure_streaming,
    stop_streaming,
    list_camera_sockets,
    order_camera_sockets,
    CameraRelayPublisher,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_FPS,
    H264Decoder,
    build_ffmpeg_command,
    stream_name_for_camera,
    stream_name_for_socket,
    CAMERA_LAYOUT_SOCKET_ORDER,
    _resolve_candidate_sockets,
)


def ensure_streaming(*, recording_manager=None, **kwargs):
    """Compat wrapper: ignores recording_manager parameter."""
    return _ensure_streaming(**kwargs)
