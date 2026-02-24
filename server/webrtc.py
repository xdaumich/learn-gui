"""Re-exports from telemetry_console.camera for backward compatibility."""

from telemetry_console.camera import (  # noqa: F401
    list_camera_sockets,
    order_camera_sockets,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_FPS,
    stream_name_for_camera,
    stream_name_for_socket,
    CAMERA_LAYOUT_SOCKET_ORDER,
    CAMERA_STREAM_LAYOUT,
    _resolve_candidate_sockets,
)
