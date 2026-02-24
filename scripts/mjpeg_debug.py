"""Standalone MJPEG debug server for OAK cameras.

Streams MJPEG from connected OAK cameras over plain HTTP.
No dependency on tc-camera, MediaMTX, tc-gui, or any other service.

Usage:
    uv run --project server python scripts/mjpeg_debug.py
    # or: make mjpeg
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager

import depthai as dai
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse

logger = logging.getLogger("mjpeg_debug")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST = os.environ.get("MJPEG_HOST", "0.0.0.0")
PORT = int(os.environ.get("MJPEG_PORT", "8001"))
WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
FPS = int(os.environ.get("CAMERA_FPS", "30"))

LAYOUT = ("left", "center", "right")
_OAK_D_PREFIX = "OAK-D"

# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------


def _discover_cameras() -> list[tuple[str, dai.DeviceInfo]]:
    """Discover connected OAK cameras and return (layout_name, device_info) pairs.

    Ordering: OAK-D models get center slot priority, matching camera.py logic.
    """
    available = dai.Device.getAllAvailableDevices()
    if not available:
        return []

    # Profile devices: (is_oak_d, name, info)
    profiles: list[tuple[bool, str, dai.DeviceInfo]] = []
    for info in available:
        try:
            name = info.name or info.deviceId
        except Exception:
            name = info.deviceId
        is_oak_d = name.upper().startswith(_OAK_D_PREFIX)
        profiles.append((is_oak_d, name, info))

    # Sort: OAK-D first (for center priority), then by name
    profiles.sort(key=lambda p: (not p[0], p[1]))

    # Apply OAK-D center-slot ordering
    oak_d = [(n, i) for is_d, n, i in profiles if is_d]
    other = [(n, i) for is_d, n, i in profiles if not is_d]

    if oak_d:
        if len(other) >= 2:
            ordered = [other[0], oak_d[0], other[1]]
        elif len(other) == 1:
            ordered = [other[0], oak_d[0]]
        else:
            ordered = list(oak_d)
    else:
        ordered = list(other)

    # Map to layout names (first 3 only)
    result: list[tuple[str, dai.DeviceInfo]] = []
    for i, (name, info) in enumerate(ordered[:3]):
        result.append((LAYOUT[i], info))
    return result


# ---------------------------------------------------------------------------
# DepthAI MJPEG pipeline
# ---------------------------------------------------------------------------


def _build_mjpeg_pipeline(device: dai.Device) -> tuple[dai.Pipeline, dai.MessageQueue]:
    """Build a DepthAI pipeline: Camera → MJPEG VideoEncoder.

    Returns (pipeline, output_queue).
    """
    pipeline = dai.Pipeline(device)

    cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    cam_out = cam.requestOutput((WIDTH, HEIGHT), dai.ImgFrame.Type.NV12, fps=FPS)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(FPS, dai.VideoEncoderProperties.Profile.MJPEG)
    encoder.setQuality(80)

    cam_out.link(encoder.input)
    queue = encoder.out.createOutputQueue(maxSize=4, blocking=False)

    return pipeline, queue


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_cameras: dict[str, str] = {}  # name → name (for /cameras)
_devices: dict[str, dai.Device] = {}
_pipelines: dict[str, dai.Pipeline] = {}
_queues: dict[str, dai.MessageQueue] = {}


def _open_devices():
    """Discover cameras and open DepthAI devices eagerly."""
    discovered = _discover_cameras()
    if not discovered:
        logger.warning("No OAK cameras found!")
        return

    for layout_name, device_info in discovered:
        device = None
        try:
            device = dai.Device(device_info)
            pipeline, queue = _build_mjpeg_pipeline(device)
            pipeline.start()
            _cameras[layout_name] = layout_name
            _devices[layout_name] = device
            _pipelines[layout_name] = pipeline
            _queues[layout_name] = queue
            logger.info("Opened camera: %s (%s)", layout_name, device_info.deviceId)
        except Exception:
            logger.exception("Failed to open camera %s", layout_name)
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass


def _close_devices():
    """Gracefully close all DepthAI devices."""
    for name, pipeline in _pipelines.items():
        try:
            pipeline.stop()
        except Exception:
            logger.exception("Error stopping pipeline %s", name)
    for name, device in _devices.items():
        try:
            device.close()
            logger.info("Closed camera: %s", name)
        except Exception:
            logger.exception("Error closing camera %s", name)
    _pipelines.clear()
    _devices.clear()
    _queues.clear()
    _cameras.clear()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _open_devices()
    yield
    _close_devices()


app = FastAPI(title="MJPEG Debug Server", lifespan=_lifespan)


@app.get("/cameras")
async def cameras() -> list[str]:
    return list(_cameras.keys())


@app.get("/stream/{camera}")
async def stream(camera: str):
    if camera not in _queues:
        return Response(status_code=404, content=f"Camera '{camera}' not found")

    queue = _queues[camera]

    async def generate():
        loop = asyncio.get_event_loop()
        while True:
            try:
                # Non-blocking get with timeout to allow cancellation checks
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


@app.get("/", response_class=HTMLResponse)
async def index():
    if not _cameras:
        return "<html><body><h1>No cameras found</h1></body></html>"

    img_tags = []
    for name in _cameras:
        img_tags.append(
            f'<div style="display:inline-block;margin:8px;text-align:center">'
            f"<h3>{name}</h3>"
            f'<img src="/stream/{name}" width="{WIDTH}" height="{HEIGHT}" '
            f'style="border:1px solid #333" />'
            f"</div>"
        )

    return (
        "<html><head><title>MJPEG Debug</title></head>"
        '<body style="background:#111;color:#eee;font-family:sans-serif;text-align:center">'
        "<h1>MJPEG Debug Viewer</h1>"
        + "".join(img_tags)
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Graceful shutdown on Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    logger.info("Starting MJPEG debug server on %s:%d", HOST, PORT)
    logger.info("Resolution: %dx%d @ %d FPS", WIDTH, HEIGHT, FPS)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
