"""FastAPI app for GUI/API process in split-runner mode."""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

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
    camera_sockets = getattr(app.state, "camera_sockets", None)
    if not camera_sockets:
        # In split-runner mode, camera relay runs in tc-camera. Avoid probing the
        # device from GUI API to prevent DepthAI contention and startup stalls.
        layout_sockets = getattr(webrtc, "CAMERA_LAYOUT_SOCKET_ORDER", ())
        camera_sockets = list(layout_sockets)

    if not camera_sockets:
        return []

    order_camera_sockets = getattr(webrtc, "order_camera_sockets", None)
    if callable(order_camera_sockets):
        camera_sockets = order_camera_sockets(camera_sockets)
    return [socket.name for socket in camera_sockets]


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
