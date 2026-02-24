"""FastAPI app for GUI/API process in split-runner mode."""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_log import RecordingManager
import rerun_bridge
import webrtc
from telemetry_console.schemas import RecordingStatus


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    yield
    webrtc.stop_streaming()


app = FastAPI(title="Telemetry Console GUI API", lifespan=_app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_log_dir() -> Path:
    env_dir = os.environ.get("DATA_LOG_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "data_logs").resolve()


def _resolve_robot_heartbeat_path() -> Path:
    env_path = os.environ.get("ROBOT_HEARTBEAT_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (_resolve_log_dir() / ".robot_heartbeat.json").resolve()


def _get_recording_manager() -> RecordingManager:
    log_dir = _resolve_log_dir()
    manager = getattr(app.state, "recording_manager", None)
    if manager is None or manager.base_dir != log_dir:
        manager = RecordingManager(log_dir)
        app.state.recording_manager = manager
    return manager


def _recording_status_from_state(state) -> RecordingStatus:
    return RecordingStatus(
        active=state.active,
        run_id=state.run_id,
        samples=state.samples,
        state=state.state,
    )


def _camera_names_from_mediamtx_paths() -> list[str] | None:
    """Read active camera stream names from MediaMTX path API.

    Returns stream names in layout order when possible.
    """
    paths_api_url = os.environ.get(
        "MEDIAMTX_PATHS_API_URL",
        "http://127.0.0.1:9997/v3/paths/list",
    )
    timeout_s = float(os.environ.get("MEDIAMTX_PATHS_API_TIMEOUT_S", "0.8"))

    try:
        with urllib_request.urlopen(paths_api_url, timeout=max(0.1, timeout_s)) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except (
        OSError,
        ValueError,
        urllib_error.HTTPError,
        urllib_error.URLError,
    ):
        return None

    items = payload.get("items")
    if not isinstance(items, list):
        return None

    # Include active tc-camera stream targets so the client can connect all
    # announced streams even while MediaMTX is still publishing paths.
    active_stream_names = getattr(webrtc, "list_stream_names", lambda: [])() or []
    active_names = [
        name.lower() for name in active_stream_names if isinstance(name, str) and name
    ]

    # Gather supported stream names from currently known MediaMTX paths.
    discovered_camera_names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path_name = item.get("name")
        if not isinstance(path_name, str):
            continue
        camera_name = path_name.lower()
        if camera_name not in ("left", "center", "right"):
            if not camera_name.startswith("cam_"):
                continue
        discovered_camera_names.append(camera_name)

    discovered_set = set(discovered_camera_names) | set(active_names)
    if not discovered_set:
        return []

    # Keep deterministic left/center/right ordering when the layout is known.
    layout_names = list(getattr(webrtc, "CAMERA_STREAM_LAYOUT", ("left", "center", "right")))
    ordered = [name for name in layout_names if name in discovered_set]
    extras = sorted(name for name in discovered_set if name not in set(layout_names))
    return ordered + extras


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rerun/status")
async def rerun_status():
    return {
        "running": rerun_bridge.is_running(),
        "web_url": rerun_bridge.web_url(),
        "grpc_url": getattr(rerun_bridge, "grpc_url", lambda: None)(),
    }


@app.get("/robot/status")
async def robot_status():
    heartbeat_path = _resolve_robot_heartbeat_path()
    try:
        max_age_s = float(os.environ.get("ROBOT_HEARTBEAT_MAX_AGE_S", "5.0"))
    except (TypeError, ValueError):
        max_age_s = 5.0
    payload = {
        "alive": False,
        "age_s": None,
        "step_count": 0,
        "path": str(heartbeat_path),
    }

    if not heartbeat_path.is_file():
        return payload

    try:
        raw = heartbeat_path.read_text(encoding="utf-8")
        heartbeat = json.loads(raw)
    except Exception as exc:
        payload["error"] = f"invalid heartbeat payload: {exc}"
        return payload

    updated_at = heartbeat.get("updated_at_s")
    if not isinstance(updated_at, (int, float)):
        payload["error"] = "heartbeat payload missing updated_at_s"
        return payload

    age_s = max(0.0, time.time() - float(updated_at))
    step_count = heartbeat.get("step_count")
    alive_flag = heartbeat.get("alive")
    payload["age_s"] = age_s
    payload["step_count"] = int(step_count) if isinstance(step_count, (int, float)) else 0
    payload["alive"] = bool(alive_flag) and age_s <= max_age_s
    return payload


@app.get("/webrtc/cameras")
async def webrtc_cameras() -> list[str]:
    # Prefer MediaMTX runtime paths so the GUI only requests streams that are
    # actually present (important when fewer than CAM_A/CAM_B/CAM_C are plugged in).
    camera_names = _camera_names_from_mediamtx_paths()
    if camera_names is not None:
        return camera_names

    camera_sockets = getattr(app.state, "camera_sockets", None)
    if not camera_sockets:
        stream_names = getattr(webrtc, "list_stream_names", lambda: None)()
        if stream_names:
            return stream_names
        # In split-runner mode, camera relay runs in tc-camera. Avoid probing the
        # device from GUI API to prevent DepthAI contention and startup stalls.
        # Return an empty list until relay paths are visible from MediaMTX.
        return []

    order_camera_sockets = getattr(webrtc, "order_camera_sockets", None)
    if callable(order_camera_sockets):
        camera_sockets = order_camera_sockets(camera_sockets)
    else:
        camera_sockets = list(camera_sockets)

    socket_to_stream_name = {
        "CAM_B": "left",
        "CAM_A": "center",
        "CAM_C": "right",
    }
    stream_names: list[str] = []
    for socket in camera_sockets:
        socket_name = str(getattr(socket, "name", socket)).upper()
        mapped_name = socket_to_stream_name.get(socket_name)
        if mapped_name is None:
            stream_names.append(socket_name.lower())
        else:
            stream_names.append(mapped_name)
    return stream_names


@app.get("/recording/status", response_model=RecordingStatus)
async def recording_status() -> RecordingStatus:
    state = _get_recording_manager().status()
    return _recording_status_from_state(state)


@app.post("/recording/start", response_model=RecordingStatus)
async def recording_start() -> RecordingStatus:
    state = _get_recording_manager().start()
    return _recording_status_from_state(state)


@app.post("/recording/stop", response_model=RecordingStatus)
async def recording_stop() -> RecordingStatus:
    state = _get_recording_manager().stop()
    return _recording_status_from_state(state)
