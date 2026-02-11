"""FastAPI entry point -- all routes start here."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_log import RecordingManager
import rerun_bridge
import webrtc
from schemas import RecordingStatus


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    yield
    webrtc.stop_streaming()


app = FastAPI(title="Telemetry Console API", lifespan=_app_lifespan)

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
    return (Path(__file__).resolve().parents[1] / "data_logs").resolve()


def _get_recording_manager() -> RecordingManager:
    log_dir = _resolve_log_dir()
    manager = getattr(app.state, "recording_manager", None)
    if manager is None or manager.base_dir != log_dir:
        manager = RecordingManager(log_dir)
        app.state.recording_manager = manager
    return manager


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rerun/status")
async def rerun_status():
    """Return the current state of the Rerun bridge."""
    return {
        "running": rerun_bridge.is_running(),
        "web_url": rerun_bridge.web_url(),
    }


@app.get("/webrtc/cameras")
async def webrtc_cameras() -> list[str]:
    camera_sockets = getattr(app.state, "camera_sockets", None)
    if camera_sockets is None:
        camera_sockets = webrtc.list_camera_sockets()
    if not camera_sockets:
        return []

    recording_manager = _get_recording_manager()
    try:
        active_sockets = webrtc.ensure_streaming(
            camera_sockets=camera_sockets,
            recording_manager=recording_manager,
        )
    except ValueError as exc:
        print(f"[webrtc] Failed to initialize camera relay: {exc}")
        return []

    return [socket.name for socket in active_sockets]


@app.get("/recording/status", response_model=RecordingStatus)
async def recording_status() -> RecordingStatus:
    state = _get_recording_manager().status()
    return RecordingStatus(**state.__dict__)


@app.post("/recording/start", response_model=RecordingStatus)
async def recording_start() -> RecordingStatus:
    state = _get_recording_manager().start()
    return RecordingStatus(**state.__dict__)


@app.post("/recording/stop", response_model=RecordingStatus)
async def recording_stop() -> RecordingStatus:
    state = _get_recording_manager().stop()
    return RecordingStatus(**state.__dict__)


# TODO: add telemetry ingestion routes
# TODO: add WebSocket sync endpoint
