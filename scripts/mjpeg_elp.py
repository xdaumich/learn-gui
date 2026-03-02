"""Standalone MJPEG server for ELP Global Shutter USB cameras.

Streams raw MJPEG from connected ELP cameras over plain HTTP.
Zero decode/encode — cameras output MJPEG on-sensor, ffmpeg passes
through raw JPEG bytes via ``-c:v copy``.

Modeled on ``scripts/mjpeg_debug.py`` (OAK MJPEG server), but uses
V4L2/ffmpeg capture instead of DepthAI.

Usage:
    uv run --project server python scripts/mjpeg_elp.py
    # or: make mjpeg_elp
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import signal
import subprocess
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse

logger = logging.getLogger("mjpeg_elp")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST = os.environ.get("MJPEG_ELP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MJPEG_ELP_PORT", "8002"))
WIDTH = int(os.environ.get("ELP_WIDTH", "640"))
HEIGHT = int(os.environ.get("ELP_HEIGHT", "480"))
FPS = int(os.environ.get("ELP_FPS", "30"))

ELP_VENDOR_ID = "32e4"
ELP_MODEL_ID = "0234"

# JPEG markers
_SOI = b"\xff\xd8"
_EOI = b"\xff\xd9"

# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------


def _discover_elp_devices() -> list[tuple[str, str]]:
    """Discover ELP cameras via udevadm.

    Returns list of (name, device_path) pairs, e.g.
    [("elp_1", "/dev/video8"), ("elp_2", "/dev/video10")].

    Each physical camera creates two /dev/video* nodes (capture + metadata).
    We group by ID_PATH and take the lower-numbered device per USB path.
    """
    video_devices = sorted(glob.glob("/dev/video*"))
    if not video_devices:
        return []

    # Group devices by USB path, filtering for ELP vendor/model.
    by_path: dict[str, list[str]] = {}
    for dev in video_devices:
        try:
            result = subprocess.run(
                ["udevadm", "info", "--query=property", dev],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            continue

        props: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                props[k.strip()] = v.strip()

        if (
            props.get("ID_VENDOR_ID") == ELP_VENDOR_ID
            and props.get("ID_MODEL_ID") == ELP_MODEL_ID
        ):
            id_path = props.get("ID_PATH", dev)
            by_path.setdefault(id_path, []).append(dev)

    # Take lowest-numbered device per USB path (capture node, not metadata).
    devices: list[str] = []
    for _path, devs in sorted(by_path.items()):
        devs.sort(key=lambda d: int(d.replace("/dev/video", "")))
        devices.append(devs[0])

    # Assign names.
    result_list: list[tuple[str, str]] = []
    for i, dev in enumerate(devices, start=1):
        result_list.append((f"elp_{i}", dev))

    return result_list


# ---------------------------------------------------------------------------
# ffmpeg MJPEG capture (raw pass-through)
# ---------------------------------------------------------------------------


class MJPEGCapture:
    """Captures raw MJPEG frames from a V4L2 device via ffmpeg -c:v copy.

    A background thread reads ffmpeg stdout and splits on JPEG SOI/EOI
    markers.  The latest complete frame is always available via ``get()``.
    """

    def __init__(self, device: str, width: int, height: int, fps: int) -> None:
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps

        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._new_frame = threading.Event()

    def start(self) -> None:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", f"{self._width}x{self._height}",
            "-framerate", str(self._fps),
            "-i", self._device,
            "-c:v", "copy",
            "-f", "image2pipe",
            "pipe:1",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("Started ffmpeg capture: %s (%dx%d@%d)", self._device, self._width, self._height, self._fps)

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def get(self, timeout: float = 1.0) -> bytes | None:
        """Block until a new frame is available, then return it."""
        if self._new_frame.wait(timeout=timeout):
            self._new_frame.clear()
            with self._lock:
                return self._frame
        return None

    def _read_loop(self) -> None:
        """Read ffmpeg stdout, split on JPEG SOI/EOI markers."""
        assert self._proc is not None
        assert self._proc.stdout is not None
        buf = bytearray()
        in_frame = False
        chunk_size = 65536

        while not self._stop.is_set():
            data = self._proc.stdout.read(chunk_size)
            if not data:
                break
            buf.extend(data)

            # Scan for complete JPEG frames.
            while True:
                if not in_frame:
                    soi = buf.find(_SOI)
                    if soi == -1:
                        # No SOI found — discard everything before potential partial marker.
                        if len(buf) > 1:
                            buf = buf[-1:]
                        break
                    # Discard bytes before SOI.
                    if soi > 0:
                        buf = buf[soi:]
                    in_frame = True

                # in_frame == True: look for EOI.
                eoi = buf.find(_EOI, 2)  # skip the SOI bytes
                if eoi == -1:
                    break

                # Complete frame: SOI .. EOI (inclusive).
                frame_end = eoi + 2
                frame = bytes(buf[:frame_end])
                buf = buf[frame_end:]
                in_frame = False

                with self._lock:
                    self._frame = frame
                self._new_frame.set()


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_cameras: dict[str, str] = {}  # name → device path
_captures: dict[str, MJPEGCapture] = {}


def _open_devices() -> None:
    devices = _discover_elp_devices()
    if not devices:
        logger.warning("No ELP cameras found!")
        return

    for name, dev_path in devices:
        cap = MJPEGCapture(dev_path, WIDTH, HEIGHT, FPS)
        try:
            cap.start()
            _cameras[name] = dev_path
            _captures[name] = cap
            logger.info("Opened camera: %s → %s", name, dev_path)
        except Exception:
            logger.exception("Failed to start capture for %s (%s)", name, dev_path)
            cap.stop()


def _close_devices() -> None:
    for name, cap in _captures.items():
        try:
            cap.stop()
            logger.info("Closed camera: %s", name)
        except Exception:
            logger.exception("Error closing camera %s", name)
    _captures.clear()
    _cameras.clear()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _open_devices()
    signal.signal(signal.SIGINT, lambda *_: os._exit(0))
    yield
    _close_devices()


app = FastAPI(title="ELP MJPEG Server", lifespan=_lifespan)


@app.get("/cameras")
async def cameras() -> list[str]:
    return list(_cameras.keys())


@app.get("/stream/{camera}")
async def stream(camera: str):
    if camera not in _captures:
        return Response(status_code=404, content=f"Camera '{camera}' not found")

    cap = _captures[camera]

    async def generate():
        loop = asyncio.get_event_loop()
        while True:
            try:
                frame = await loop.run_in_executor(None, lambda: cap.get(timeout=2.0))
                if frame is None:
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                    b"\r\n" + frame + b"\r\n"
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
        return "<html><body><h1>No ELP cameras found</h1></body></html>"

    names = sorted(_cameras.keys())

    def _tile(name: str) -> str:
        label = name.replace("_", " ").upper()
        return (
            f'<div style="text-align:center">'
            f'<div style="font-size:13px;color:#888;margin-bottom:4px">{label}</div>'
            f'<img src="/stream/{name}" '
            f'style="max-width:{WIDTH}px;width:100%;height:auto;'
            f'border:1px solid #333;border-radius:4px" />'
            f"</div>"
        )

    tiles = "".join(_tile(n) for n in names)
    grid = (
        f'<div style="display:flex;justify-content:center;gap:16px;flex-wrap:wrap">'
        f"{tiles}</div>"
    )

    return (
        "<html><head><title>ELP MJPEG</title></head>"
        '<body style="background:#111;color:#eee;font-family:sans-serif;'
        'text-align:center;padding:16px">'
        '<h1 style="margin:0 0 16px 0;font-size:20px">ELP MJPEG Viewer</h1>'
        + grid
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _cleanup_previous() -> None:
    """Kill any previous process on our HTTP port."""
    try:
        subprocess.run(
            ["fuser", "-k", "-KILL", f"{PORT}/tcp"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    signal.signal(signal.SIGINT, lambda *_: os._exit(0))

    _cleanup_previous()

    logger.info("Starting ELP MJPEG server on %s:%d", HOST, PORT)
    logger.info("Resolution: %dx%d @ %d FPS", WIDTH, HEIGHT, FPS)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
