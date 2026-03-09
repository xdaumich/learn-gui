"""FastAPI app for GUI/API process in split-runner mode."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import depthai as dai
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from data_log import RecordingManager
import rerun_bridge
from telemetry_console.camera import (
    CAMERA_STREAM_LAYOUT,
    _discover_device_profiles,
    _load_slot_map,
    build_mjpeg_pipeline,
)
from telemetry_console.schemas import RecordingStatus

_log = logging.getLogger("tc.gui_api")

# ---------------------------------------------------------------------------
# MJPEG camera manager (replaces WebRTC SessionManager)
# ---------------------------------------------------------------------------

_cameras: dict[str, str] = {}
_devices: dict[str, dai.Device] = {}
_pipelines: dict[str, dai.Pipeline] = {}
_queues: dict[str, dai.MessageQueue] = {}


def _open_cameras(*, min_cameras: int = 0, timeout_s: float = 30.0, retry_s: float = 2.0):
    """Discover OAK cameras, open MJPEG pipelines, assign layout slots."""
    import time as _time

    deadline = _time.monotonic() + max(0.1, timeout_s) if min_cameras > 0 else 0.0

    while True:
        # Discover devices not yet opened.
        all_profiles = _discover_device_profiles()
        new_profiles = [p for p in all_profiles if p.device_id not in {
            str(getattr(d.getDeviceInfo(), "deviceId", "")) for d in _devices.values()
        }]

        if new_profiles:
            # Slot assignment: config-driven or auto OAK-D center heuristic.
            slot_map = _load_slot_map()
            if slot_map:
                profiles_by_id = {p.device_id: p for p in new_profiles}
                for slot in CAMERA_STREAM_LAYOUT:
                    if slot in _cameras:
                        continue
                    if slot in slot_map and slot_map[slot] in profiles_by_id:
                        profile = profiles_by_id[slot_map[slot]]
                        _open_single(slot, profile.device_info)
            else:
                oak_d = [p for p in new_profiles if p.is_oak_d]
                other = [p for p in new_profiles if not p.is_oak_d]
                if oak_d:
                    if len(other) >= 2:
                        ordered = [other[0], oak_d[0], other[1]]
                    elif len(other) == 1:
                        ordered = [other[0], oak_d[0]]
                    else:
                        ordered = list(oak_d)
                else:
                    ordered = list(new_profiles)

                slot_iter = iter(ordered)
                for slot in CAMERA_STREAM_LAYOUT:
                    if slot in _cameras:
                        continue
                    profile = next(slot_iter, None)
                    if profile is not None:
                        _open_single(slot, profile.device_info)

        opened = [s for s in CAMERA_STREAM_LAYOUT if s in _cameras]
        if len(opened) >= min_cameras or _time.monotonic() >= deadline or min_cameras <= 0:
            _log.info(
                "Camera discovery done: %d/%d (%s)",
                len(opened), min_cameras, ", ".join(opened) or "none",
            )
            return opened

        _log.info(
            "Found %d/%d cameras, retrying in %.0fs...",
            len(opened), min_cameras, retry_s,
        )
        _time.sleep(retry_s)


def _open_single(slot: str, device_info: dai.DeviceInfo):
    try:
        device = dai.Device(device_info)
        pipeline, queue = build_mjpeg_pipeline(device=device)
        pipeline.start()
        _cameras[slot] = slot
        _devices[slot] = device
        _pipelines[slot] = pipeline
        _queues[slot] = queue
        _log.info("Opened camera: %s (%s)", slot, device.getDeviceName())
    except Exception:
        _log.exception("Failed to open camera %s", slot)


def _close_cameras():
    for name, pipeline in _pipelines.items():
        try:
            pipeline.stop()
        except Exception:
            _log.exception("Error stopping pipeline %s", name)
    for name, device in _devices.items():
        try:
            device.close()
            _log.info("Closed camera: %s", name)
        except Exception:
            _log.exception("Error closing camera %s", name)
    _pipelines.clear()
    _devices.clear()
    _queues.clear()
    _cameras.clear()


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    min_cameras = int(os.environ.get("MIN_CAMERAS", "3"))
    _open_cameras(min_cameras=min_cameras)
    yield
    _close_cameras()


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


@app.get("/cameras")
async def cameras() -> list[str]:
    return [s for s in CAMERA_STREAM_LAYOUT if s in _cameras]


@app.get("/stream/{camera}")
async def stream(camera: str):
    if camera not in _queues:
        return Response(status_code=404, content=f"Camera '{camera}' not found")

    queue = _queues[camera]

    async def generate():
        loop = asyncio.get_event_loop()
        while True:
            try:
                frame = await loop.run_in_executor(None, lambda: queue.get())
                jpeg_data = frame.getData().tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg_data)).encode() + b"\r\n"
                    b"\r\n" + jpeg_data + b"\r\n"
                )
            except Exception:
                break

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


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
