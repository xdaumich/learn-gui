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
    Uses DeviceInfo only (no device open) — model name detection happens in
    _open_devices after opening, which may reorder slots.
    """
    available = dai.Device.getAllAvailableDevices()
    if not available:
        return []
    # Return raw infos; _open_devices handles ordering after getting model names.
    return available[:3]


def _assign_layout(opened: list[tuple[str, dai.Device]]) -> list[tuple[str, dai.Device]]:
    """Reorder opened devices so OAK-D gets the center slot.

    opened: list of (model_name, device) in discovery order.
    Returns: list of (layout_name, device) with correct slot assignment.
    """
    oak_d = [(n, d) for n, d in opened if n.upper().startswith(_OAK_D_PREFIX)]
    other = [(n, d) for n, d in opened if not n.upper().startswith(_OAK_D_PREFIX)]
    other.reverse()

    if oak_d:
        if len(other) >= 2:
            ordered = [other[0], oak_d[0], other[1]]
        elif len(other) == 1:
            ordered = [other[0], oak_d[0]]
        else:
            ordered = list(oak_d)
    else:
        ordered = list(other)

    result: list[tuple[str, dai.Device]] = []
    for i, (model_name, device) in enumerate(ordered[:3]):
        result.append((LAYOUT[i], device))
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
    """Discover cameras, open devices, and assign layout slots.

    Opens all devices first to read the real model name (getDeviceName),
    then assigns layout slots with OAK-D center priority.
    """
    infos = _discover_cameras()
    if not infos:
        logger.warning("No OAK cameras found!")
        return

    # Phase 1: open devices and read model names.
    opened: list[tuple[str, dai.Device]] = []
    for info in infos:
        try:
            device = dai.Device(info)
            model = device.getDeviceName()
            logger.info("Discovered %s (%s)", model, info.deviceId)
            opened.append((model, device))
        except Exception:
            logger.exception("Failed to open device %s", info.deviceId)

    if not opened:
        return

    # Phase 2: assign layout slots (OAK-D → center).
    assigned = _assign_layout(opened)

    # Phase 3: build and start pipelines.
    for layout_name, device in assigned:
        try:
            pipeline, queue = _build_mjpeg_pipeline(device)
            pipeline.start()
            _cameras[layout_name] = layout_name
            _devices[layout_name] = device
            _pipelines[layout_name] = pipeline
            _queues[layout_name] = queue
            logger.info("Opened camera: %s (%s)", layout_name, device.getDeviceName())
        except Exception:
            logger.exception("Failed to start pipeline for %s", layout_name)
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

    names = list(_cameras.keys())

    def _tile(name: str, w: int, h: int) -> str:
        label = name.capitalize()
        return (
            f'<div style="text-align:center">'
            f'<div style="font-size:13px;color:#888;margin-bottom:4px">{label}</div>'
            f'<img src="/stream/{name}" width="{w}" height="{h}" '
            f'style="border:1px solid #333;border-radius:4px" />'
            f"</div>"
        )

    # Center (OAK-D) on top row, left/right on bottom row
    top_row = ""
    bottom_tiles: list[str] = []
    side_w, side_h = int(WIDTH * 0.75), int(HEIGHT * 0.75)

    for name in names:
        if name == "center":
            top_row = (
                f'<div style="margin-bottom:12px">'
                f"{_tile(name, WIDTH, HEIGHT)}"
                f"</div>"
            )
        else:
            bottom_tiles.append(_tile(name, side_w, side_h))

    bottom_row = ""
    if bottom_tiles:
        bottom_row = (
            '<div style="display:flex;justify-content:center;gap:16px">'
            + "".join(bottom_tiles)
            + "</div>"
        )

    return (
        "<html><head><title>MJPEG Debug</title></head>"
        '<body style="background:#111;color:#eee;font-family:sans-serif;'
        'text-align:center;padding:16px">'
        '<h1 style="margin:0 0 16px 0;font-size:20px">MJPEG Debug Viewer</h1>'
        + top_row + bottom_row
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_OAK_VENDOR = "03e7"
_OAK_BOOTED_PRODUCT = "2485"   # MyriadX in BOOTED state
_OAK_UNBOOTED_PRODUCT = "f63b"  # Myriad VPU in UNBOOTED state
_USB_RECYCLE_TIMEOUT = 15  # seconds to wait for BOOTED → UNBOOTED


def _find_oak_usb_devices() -> list[tuple[str, str, str]]:
    """Return list of (bus, device, product_id) for all OAK USB devices."""
    import re
    import subprocess

    try:
        out = subprocess.run(
            ["lsusb", "-d", f"{_OAK_VENDOR}:"],
            capture_output=True, text=True,
        ).stdout
    except FileNotFoundError:
        return []

    results = []
    for line in out.strip().splitlines():
        m = re.match(r"Bus (\d+) Device (\d+): ID \w+:(\w+)", line)
        if m:
            results.append((m.group(1), m.group(2), m.group(3)))
    return results


def _kill_oak_holders():
    """Find and kill any process holding OAK USB device files."""
    import subprocess

    devices = _find_oak_usb_devices()
    if not devices:
        return False

    killed_any = False
    my_pid = os.getpid()

    for bus, dev, _prod in devices:
        dev_path = f"/dev/bus/usb/{bus}/{dev}"
        try:
            result = subprocess.run(
                ["fuser", dev_path],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                continue
            pids = result.stdout.split()
            for pid_str in pids:
                pid = int(pid_str.strip().rstrip("m"))
                if pid == my_pid:
                    continue
                logger.info("Killing PID %d holding %s", pid, dev_path)
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed_any = True
                except PermissionError:
                    # Root-owned process — escalate with sudo.
                    logger.info("Escalating to sudo kill -9 %d", pid)
                    subprocess.run(["sudo", "kill", "-9", str(pid)])
                    killed_any = True
                except ProcessLookupError:
                    pass
        except FileNotFoundError:
            pass
    return killed_any


def _wait_usb_recycle():
    """Wait until all OAK devices are in UNBOOTED state (product f63b)."""
    import time

    deadline = time.monotonic() + _USB_RECYCLE_TIMEOUT
    while time.monotonic() < deadline:
        devices = _find_oak_usb_devices()
        booted = [d for d in devices if d[2] == _OAK_BOOTED_PRODUCT]
        if not booted:
            total = len(devices)
            logger.info("All %d OAK device(s) are UNBOOTED — ready", total)
            return True
        remaining = deadline - time.monotonic()
        logger.info(
            "%d device(s) still BOOTED, waiting... (%.0fs left)",
            len(booted), remaining,
        )
        time.sleep(1)

    booted = [d for d in _find_oak_usb_devices() if d[2] == _OAK_BOOTED_PRODUCT]
    if booted:
        logger.warning(
            "%d device(s) still BOOTED after %ds — they may fail to open",
            len(booted), _USB_RECYCLE_TIMEOUT,
        )
    return not booted


def _cleanup_previous():
    """Kill processes holding OAK cameras or our port, wait for USB recycle."""
    import subprocess

    killed = False

    # 1. Kill anything on our HTTP port.
    try:
        result = subprocess.run(
            ["fuser", "-k", "-KILL", f"{PORT}/tcp"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Killed previous process on port %d", PORT)
            killed = True
    except FileNotFoundError:
        pass

    # 2. Kill any process holding OAK USB device files.
    if _kill_oak_holders():
        killed = True

    # 3. Wait for all devices to recycle to UNBOOTED.
    if killed:
        logger.info("Waiting for OAK USB devices to recycle...")
    _wait_usb_recycle()


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Graceful shutdown on Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    _cleanup_previous()

    logger.info("Starting MJPEG debug server on %s:%d", HOST, PORT)
    logger.info("Resolution: %dx%d @ %d FPS", WIDTH, HEIGHT, FPS)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
