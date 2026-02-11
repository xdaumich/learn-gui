"""Backward-compat shim — delegates to telemetry_console.viewer."""

from telemetry_console import viewer as _viewer  # noqa: F401
from telemetry_console.viewer import (  # noqa: F401
    ARM_JOINT_NAMES,
    DEFAULT_3D_CAMERA_POSITION,
    DEFAULT_3D_CAMERA_LOOK_TARGET,
    DEFAULT_GRPC_PORT,
    DEFAULT_GRPC_URL,
    DEFAULT_WEB_PORT,
    LEFT_ARM_JOINT_NAMES,
    RIGHT_ARM_JOINT_NAMES,
    _default_eye_controls,
    _get_3d_view_contents,
    connect_grpc,
    grpc_url,
    _send_blueprint,
    get_joint_limits,
    is_running,
    load_vega_1p_model,
    log_arm_transforms,
    send_robot_blueprint,
    start,
    web_url,
    _vega_1p_urdf_path,
    _running,
    _web_url,
    _grpc_url,
    _urdf_tree,
    _robot_root,
)

# Demo-only streaming (kept here, not in SDK)
import math
import time

import rerun as rr


def _log_series_style() -> None:
    """Log static SeriesLines style so the plot looks nice."""
    rr.log(
        "trajectory/sin",
        rr.SeriesLines(colors=[0, 255, 128], names=["sin"]),
        static=True,
    )
    rr.log(
        "trajectory/cos",
        rr.SeriesLines(colors=[128, 140, 255], names=["cos"]),
        static=True,
    )


def _log_shoulder_transforms(sin_value: float, cos_value: float) -> None:
    """Log joint transforms for the shoulder joints if the URDF is loaded."""
    from telemetry_console import viewer
    if viewer._urdf_tree is None or not hasattr(viewer._urdf_tree, "get_joint_by_name"):
        return

    robot_root = viewer._robot_root or f"/{_vega_1p_urdf_path().stem}"
    joint_updates = (("L_arm_j1", sin_value), ("R_arm_j1", cos_value))

    for joint_name, joint_value in joint_updates:
        joint = viewer._urdf_tree.get_joint_by_name(joint_name)
        if joint is None:
            continue
        transform = joint.compute_transform(joint_value)
        rr.log(f"{robot_root}/joint_transforms/{joint.name}", transform)


def stream_sine_wave(*, hz: float = 20.0, duration: float | None = None) -> None:
    """Stream a sine + cosine wave at *hz* updates/sec."""
    _log_series_style()

    interval = 1.0 / hz
    t0 = time.time()

    while True:
        t = time.time()
        rr.set_time("wall_time", timestamp=t)
        sin_value = math.sin(t * 2.0 * math.pi)
        cos_value = math.cos(t * 2.0 * math.pi)
        rr.log("trajectory/sin", rr.Scalars(sin_value))
        rr.log("trajectory/cos", rr.Scalars(cos_value))
        _log_shoulder_transforms(sin_value, cos_value)

        if duration is not None and (t - t0) >= duration:
            break

        time.sleep(interval)
