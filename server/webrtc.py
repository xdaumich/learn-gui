"""Re-exports from telemetry_console.camera for backward compatibility."""

import av  # noqa: F401

from telemetry_console.camera import (  # noqa: F401
    ensure_streaming,
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
    CAMERA_STREAM_LAYOUT,
    _resolve_candidate_sockets,
    list_stream_names,
)
