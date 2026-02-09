"""FastAPI entry point -- all routes start here."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_log import RecordingManager
import rerun_bridge
import webrtc
from schemas import RecordingStatus, SDPOffer, SDPAnswer

app = FastAPI(title="Telemetry Console API")

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


@app.post("/webrtc/offer", response_model=SDPAnswer)
async def webrtc_offer(offer: SDPOffer) -> SDPAnswer:
    track_factory = getattr(app.state, "track_factory", None)
    camera_sockets = getattr(app.state, "camera_sockets", None)
    answer, pc = await webrtc.create_answer(
        offer.sdp,
        offer.type,
        camera_sockets=camera_sockets,
        track_factory=track_factory,
        recording_manager=_get_recording_manager(),
    )

    if not hasattr(app.state, "peer_connections"):
        app.state.peer_connections = set()
    app.state.peer_connections.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            app.state.peer_connections.discard(pc)

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange() -> None:
        if pc.iceConnectionState == "failed":
            await pc.close()
            app.state.peer_connections.discard(pc)

    return SDPAnswer(sdp=answer.sdp, type=answer.type)


@app.get("/webrtc/cameras")
async def webrtc_cameras() -> list[str]:
    camera_sockets = getattr(app.state, "camera_sockets", None)
    if camera_sockets is None:
        camera_sockets = webrtc.list_camera_sockets()
    return [socket.name for socket in camera_sockets]


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
