"""Bridge between ingested telemetry and Rerun SDK.

Provides helpers to:
- Start a Rerun gRPC server + web viewer for embedding in the frontend
- Stream a mock sine-wave trajectory for demo / testing
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import rerun as rr
import rerun.blueprint as rrb

# ---------------------------------------------------------------------------
# Default ports (match .env.example)
# ---------------------------------------------------------------------------
DEFAULT_GRPC_PORT = 9876
DEFAULT_WEB_PORT = 9090

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_running = False
_web_url: str | None = None
_urdf_tree: rr.urdf.UrdfTree | None = None
_robot_root: str | None = None


def is_running() -> bool:
    """Return whether the Rerun bridge has been started."""
    return _running


def web_url() -> str | None:
    """Return the web-viewer URL, or *None* if not started."""
    return _web_url


def _vega_1p_urdf_path() -> Path:
    """Return the absolute path to the vega_1p_f5d6 URDF file."""
    return (
        Path(__file__).resolve().parents[1]
        / "external"
        / "dexmate-urdf"
        / "robots"
        / "humanoid"
        / "vega_1p"
        / "vega_1p_f5d6.urdf"
    )


def load_vega_1p_model() -> Path | None:
    """Load the vega_1p URDF model into Rerun, if available."""
    global _robot_root, _urdf_tree  # noqa: PLW0603

    urdf_path = _vega_1p_urdf_path()
    if not urdf_path.is_file():
        print(f"[rerun_bridge] URDF not found: {urdf_path}")
        _urdf_tree = None
        _robot_root = None
        return None

    _robot_root = f"/{urdf_path.stem}"
    rr.log_file_from_path(urdf_path, static=True)
    _urdf_tree = rr.urdf.UrdfTree.from_file_path(
        urdf_path, entity_path_prefix=_robot_root
    )
    recording = rr.get_global_data_recording()
    if recording is not None:
        recording.flush()
    return urdf_path


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def start(
    *,
    grpc_port: int = DEFAULT_GRPC_PORT,
    web_port: int = DEFAULT_WEB_PORT,
    open_browser: bool = False,
) -> str:
    """Initialise Rerun, start gRPC + web-viewer servers, send blueprint.

    Returns the web-viewer URL (e.g. ``http://localhost:9090``).
    """
    global _running, _web_url  # noqa: PLW0603

    rr.init("telemetry_console")

    # Start the gRPC data server
    server_uri = rr.serve_grpc(grpc_port=grpc_port)

    # Start the HTTP server that hosts the web viewer
    rr.serve_web_viewer(
        web_port=web_port,
        open_browser=open_browser,
        connect_to=server_uri,
    )

    # Send a blueprint with a TimeSeriesView using a rolling 2-sec window
    _send_blueprint()
    load_vega_1p_model()

    _web_url = f"http://localhost:{web_port}"
    _running = True
    print(f"[rerun_bridge] gRPC  → {server_uri}")
    print(f"[rerun_bridge] Web   → {_web_url}")
    return _web_url


def _send_blueprint() -> None:
    """Push a default blueprint with trajectory + 3D views side-by-side."""
    robot_root = f"/{_vega_1p_urdf_path().stem}"
    visual_contents = [
        f"{robot_root}/visual_geometries/**",
        f"{robot_root}/joint_transforms/**",
    ]
    collision_contents = [
        f"{robot_root}/collision_geometries/**",
        f"{robot_root}/joint_transforms/**",
    ]

    blueprint = rrb.Blueprint(
        rrb.Horizontal(
            rrb.TimeSeriesView(
                origin="/trajectory",
                name="Trajectory",
                time_ranges=[
                    rrb.VisibleTimeRange(
                        "wall_time",
                        start=rrb.TimeRangeBoundary.cursor_relative(seconds=-2.0),
                        end=rrb.TimeRangeBoundary.cursor_relative(),
                    ),
                ],
            ),
            rrb.Tabs(
                rrb.Spatial3DView(
                    origin="/",
                    name="3D Visual",
                    contents=visual_contents,
                ),
                rrb.Spatial3DView(
                    origin="/",
                    name="3D Collision",
                    contents=collision_contents,
                ),
                active_tab=0,
            ),
            column_shares=[0.55, 0.45],
        ),
        collapse_panels=True,
    )
    rr.send_blueprint(blueprint, make_active=True, make_default=True)


# ---------------------------------------------------------------------------
# Static series styling
# ---------------------------------------------------------------------------

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
    if _urdf_tree is None:
        return

    robot_root = _robot_root or f"/{_vega_1p_urdf_path().stem}"
    joint_updates = (("L_arm_j1", sin_value), ("R_arm_j1", cos_value))

    for joint_name, joint_value in joint_updates:
        joint = _urdf_tree.get_joint_by_name(joint_name)
        if joint is None:
            continue
        transform = joint.compute_transform(joint_value)
        rr.log(f"{robot_root}/joint_transforms/{joint.name}", transform)


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

def stream_sine_wave(*, hz: float = 20.0, duration: float | None = None) -> None:
    """Stream a sine + cosine wave at *hz* updates/sec.

    Parameters
    ----------
    hz:
        Update rate in hertz (default 20 → 50 ms sleep).
    duration:
        Total seconds to stream.  ``None`` means *forever*.
    """
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
