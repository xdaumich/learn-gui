"""Rerun viewer lifecycle, URDF loading, blueprints, and joint-transform logging.

Shared utility extracted from ``rerun_bridge`` so that both the robot env
and replay modules can use it without pulling in demo-specific streaming code.
"""

from __future__ import annotations

import math
from pathlib import Path

import rerun as rr
import rerun.blueprint as rrb

# ---------------------------------------------------------------------------
# Default ports (match .env.example)
# ---------------------------------------------------------------------------
DEFAULT_GRPC_PORT = 9876
DEFAULT_WEB_PORT = 9090
DEFAULT_GRPC_URL = f"rerun+http://127.0.0.1:{DEFAULT_GRPC_PORT}/proxy"

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_running = False
_web_url: str | None = None
_grpc_url: str | None = None
_urdf_tree: rr.urdf.UrdfTree | None = None
_robot_root: str | None = None
LEFT_ARM_JOINT_NAMES = tuple(f"L_arm_j{i}" for i in range(1, 8))
RIGHT_ARM_JOINT_NAMES = tuple(f"R_arm_j{i}" for i in range(1, 8))
ARM_JOINT_NAMES = LEFT_ARM_JOINT_NAMES + RIGHT_ARM_JOINT_NAMES
DEFAULT_3D_CAMERA_POSITION = (1.0, 1.0, 1.0)
DEFAULT_3D_CAMERA_LOOK_TARGET = (0.0, 0.0, 0.5)


def _default_eye_controls() -> rrb.EyeControls3D:
    """Return the default 3D camera pose (x=front, y=left, z=up)."""
    return rrb.EyeControls3D(
        position=DEFAULT_3D_CAMERA_POSITION,
        look_target=DEFAULT_3D_CAMERA_LOOK_TARGET,
    )


def is_running() -> bool:
    """Return whether the Rerun bridge has been started."""
    return _running


def web_url() -> str | None:
    """Return the web-viewer URL, or *None* if not started."""
    return _web_url


def grpc_url() -> str | None:
    """Return the gRPC URL used by this process."""
    return _grpc_url


def connect_grpc(
    *,
    url: str = DEFAULT_GRPC_URL,
    app_id: str = "telemetry_console_robot",
    external_web_url: str | None = None,
) -> str:
    """Connect this process to an already-running Rerun gRPC server."""
    global _running, _web_url, _grpc_url  # noqa: PLW0603

    rr.init(app_id)
    rr.connect_grpc(url)

    _grpc_url = url
    if external_web_url is not None:
        _web_url = external_web_url
    elif _web_url is None:
        _web_url = f"http://localhost:{DEFAULT_WEB_PORT}"
    _running = True
    return url


def _vega_1p_urdf_path() -> Path:
    """Return the absolute path to the vega_1p_f5d6 URDF file."""
    return (
        Path(__file__).resolve().parents[2]
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
    global _running, _web_url, _grpc_url  # noqa: PLW0603

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
    _grpc_url = server_uri
    _running = True
    print(f"[rerun_bridge] gRPC  → {server_uri}")
    print(f"[rerun_bridge] Web   → {_web_url}")
    return _web_url


def _get_3d_view_contents(robot_root: str) -> tuple[list[str], list[str]]:
    """Return (visual_contents, collision_contents) for 3D views."""
    visual_contents = [
        f"{robot_root}/visual_geometries/**",
        f"{robot_root}/joint_transforms/**",
    ]
    collision_contents = [
        f"{robot_root}/collision_geometries/**",
        f"{robot_root}/joint_transforms/**",
    ]
    return visual_contents, collision_contents


def _send_blueprint() -> None:
    """Push a default blueprint with trajectory + 3D views side-by-side."""
    robot_root = f"/{_vega_1p_urdf_path().stem}"
    visual_contents, collision_contents = _get_3d_view_contents(robot_root)

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
                    eye_controls=_default_eye_controls(),
                ),
                rrb.Spatial3DView(
                    origin="/",
                    name="3D Collision",
                    contents=collision_contents,
                    eye_controls=_default_eye_controls(),
                ),
                active_tab=0,
            ),
            column_shares=[0.55, 0.45],
        ),
        collapse_panels=True,
    )
    rr.send_blueprint(blueprint, make_active=True, make_default=True)


def send_robot_blueprint(*, window_seconds: float = 5.0) -> None:
    """Push a blueprint optimized for robot-arm command/state tracking."""
    robot_root = f"/{_vega_1p_urdf_path().stem}"
    visual_contents, collision_contents = _get_3d_view_contents(robot_root)
    left_contents = [f"/trajectory/cmd/{name}" for name in LEFT_ARM_JOINT_NAMES] + [
        f"/trajectory/state/{name}" for name in LEFT_ARM_JOINT_NAMES
    ]
    right_contents = [f"/trajectory/cmd/{name}" for name in RIGHT_ARM_JOINT_NAMES] + [
        f"/trajectory/state/{name}" for name in RIGHT_ARM_JOINT_NAMES
    ]
    time_ranges = [
        rrb.VisibleTimeRange(
            "wall_time",
            start=rrb.TimeRangeBoundary.cursor_relative(seconds=-window_seconds),
            end=rrb.TimeRangeBoundary.cursor_relative(),
        ),
    ]

    blueprint = rrb.Blueprint(
        rrb.Horizontal(
            rrb.Vertical(
                rrb.TimeSeriesView(
                    origin="/",
                    name="Left Arm Cmd vs State",
                    contents=left_contents,
                    time_ranges=time_ranges,
                ),
                rrb.TimeSeriesView(
                    origin="/",
                    name="Right Arm Cmd vs State",
                    contents=right_contents,
                    time_ranges=time_ranges,
                ),
                row_shares=[0.5, 0.5],
            ),
            rrb.Tabs(
                rrb.Spatial3DView(
                    origin="/",
                    name="3D Visual",
                    contents=visual_contents,
                    eye_controls=_default_eye_controls(),
                ),
                rrb.Spatial3DView(
                    origin="/",
                    name="3D Collision",
                    contents=collision_contents,
                    eye_controls=_default_eye_controls(),
                ),
                active_tab=0,
            ),
            column_shares=[0.55, 0.45],
        ),
        collapse_panels=True,
    )
    rr.send_blueprint(blueprint, make_active=True, make_default=True)


def log_arm_transforms(joint_positions: dict[str, float]) -> None:
    """Log transforms for all configured arm joints."""
    if _urdf_tree is None or not hasattr(_urdf_tree, "get_joint_by_name"):
        return

    robot_root = _robot_root or f"/{_vega_1p_urdf_path().stem}"

    for joint_name in ARM_JOINT_NAMES:
        joint_value = joint_positions.get(joint_name)
        if joint_value is None:
            continue
        joint = _urdf_tree.get_joint_by_name(joint_name)
        if joint is None:
            continue
        transform = joint.compute_transform(float(joint_value))
        rr.log(f"{robot_root}/joint_transforms/{joint.name}", transform)


def get_joint_limits() -> dict[str, tuple[float, float]]:
    """Return lower/upper limits for each arm joint."""
    global _urdf_tree  # noqa: PLW0603

    if _urdf_tree is None or not hasattr(_urdf_tree, "get_joint_by_name"):
        load_vega_1p_model()

    limits: dict[str, tuple[float, float]] = {}
    for joint_name in ARM_JOINT_NAMES:
        lower = -math.pi
        upper = math.pi
        if _urdf_tree is not None:
            joint = _urdf_tree.get_joint_by_name(joint_name)
            if joint is not None:
                joint_lower = getattr(joint, "limit_lower", None)
                joint_upper = getattr(joint, "limit_upper", None)
                if joint_lower is not None:
                    lower = float(joint_lower)
                if joint_upper is not None:
                    upper = float(joint_upper)
        limits[joint_name] = (lower, upper)
    return limits
