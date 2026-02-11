"""DepthAI H.264 relay manager for MediaMTX."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Optional, Sequence

import av
import depthai as dai
import numpy as np

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 30
DEFAULT_KEYFRAME_INTERVAL = 30
DEFAULT_RTSP_TEMPLATE = "rtsp://127.0.0.1:8554/{stream_name}"
DEFAULT_FFMPEG_BIN = "ffmpeg"
CAMERA_LAYOUT_SOCKET_ORDER = (
    dai.CameraBoardSocket.CAM_B,  # Camera 2 (left mono)
    dai.CameraBoardSocket.CAM_A,  # Camera 1 (center RGB)
    dai.CameraBoardSocket.CAM_C,  # Camera 3 (right mono)
)
_CAMERA_SOCKET_ORDER_INDEX = {
    socket: index for index, socket in enumerate(CAMERA_LAYOUT_SOCKET_ORDER)
}

_state_lock = threading.Lock()
_pipeline: Optional[dai.Pipeline] = None
_pipeline_queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
_publishers: dict[dai.CameraBoardSocket, "CameraRelayPublisher"] = {}


def order_camera_sockets(
    sockets: Sequence[dai.CameraBoardSocket],
) -> list[dai.CameraBoardSocket]:
    """Order sockets to match physical layout: left, center RGB, right."""
    unique_sockets = list(dict.fromkeys(sockets))
    fallback_index = len(_CAMERA_SOCKET_ORDER_INDEX)
    return sorted(
        unique_sockets,
        key=lambda socket: (_CAMERA_SOCKET_ORDER_INDEX.get(socket, fallback_index), socket.name),
    )


def list_camera_sockets() -> list[dai.CameraBoardSocket]:
    # When a pipeline is running, reuse known sockets instead of probing the device again.
    with _state_lock:
        if _pipeline is not None and _pipeline_queues:
            return order_camera_sockets(list(_pipeline_queues.keys()))

    with dai.Device() as device:
        return order_camera_sockets(list(device.getConnectedCameras()))


def stream_name_for_camera(camera_name: str) -> str:
    return camera_name.lower()


def stream_name_for_socket(socket: dai.CameraBoardSocket) -> str:
    return stream_name_for_camera(socket.name)


def _pipeline_connected_sockets(pipeline: dai.Pipeline) -> list[dai.CameraBoardSocket]:
    try:
        features = pipeline.getDefaultDevice().getConnectedCameraFeatures()
    except Exception:
        return []

    sockets: list[dai.CameraBoardSocket] = []
    for feature in features:
        socket = getattr(feature, "socket", None)
        if socket is None:
            continue
        sockets.append(socket)
    return sockets


def _resolve_candidate_sockets(
    requested: Sequence[dai.CameraBoardSocket],
    available: Sequence[dai.CameraBoardSocket],
) -> list[dai.CameraBoardSocket]:
    if not available:
        return order_camera_sockets(requested)

    requested_set = set(requested)
    requested_available = [socket for socket in available if socket in requested_set]
    if requested_available:
        return order_camera_sockets(requested_available)

    return order_camera_sockets(available)


def _rtsp_url_for_stream(stream_name: str) -> str:
    template = os.environ.get("MEDIAMTX_RTSP_TEMPLATE", DEFAULT_RTSP_TEMPLATE)
    return template.format(stream_name=stream_name)


def build_ffmpeg_command(*, rtsp_url: str, fps: int) -> list[str]:
    ffmpeg_bin = os.environ.get("FFMPEG_BIN", DEFAULT_FFMPEG_BIN)
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-fflags",
        "+genpts",
        "-f",
        "h264",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "copy",
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        rtsp_url,
    ]


def _timestamp_ns(img: dai.ImgFrame) -> int:
    try:
        device_ts = img.getTimestampDevice()
    except Exception:
        device_ts = None

    try:
        ts = device_ts or img.getTimestamp()
    except Exception:
        ts = None

    if ts is None:
        return time.time_ns()

    try:
        return int(ts.total_seconds() * 1e9)
    except Exception:
        return time.time_ns()


class H264Decoder:
    """Decode H.264 NAL units into RGB frames."""

    def __init__(self) -> None:
        self._codec = av.CodecContext.create("h264", "r")

    def decode(self, payload: bytes) -> list[np.ndarray]:
        packet = av.Packet(payload)
        frames: list[np.ndarray] = []
        for frame in self._codec.decode(packet):
            frames.append(frame.to_ndarray(format="rgb24"))
        return frames


class CameraRelayPublisher(threading.Thread):
    def __init__(
        self,
        *,
        camera_socket: dai.CameraBoardSocket,
        queue: dai.DataOutputQueue,
        fps: int,
    ) -> None:
        super().__init__(daemon=True, name=f"relay-{camera_socket.name.lower()}")
        self._camera_socket = camera_socket
        self._queue = queue
        self._fps = max(1, fps)
        self._frame_interval_ns = int(1e9 / self._fps)
        self._stop_event = threading.Event()
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self._rtsp_url = _rtsp_url_for_stream(stream_name_for_socket(camera_socket))

    def run(self) -> None:
        self._start_ffmpeg()
        while not self._stop_event.is_set():
            packet = self._queue.tryGet()
            if packet is None:
                time.sleep(0.002)
                continue
            payload = bytes(packet.getData())
            if not payload:
                continue
            self._forward(payload)
        self._close_ffmpeg()

    def stop(self) -> None:
        self._stop_event.set()

    def _start_ffmpeg(self) -> None:
        self._close_ffmpeg()
        command = build_ffmpeg_command(rtsp_url=self._rtsp_url, fps=self._fps)
        self._ffmpeg = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _close_ffmpeg(self) -> None:
        process = self._ffmpeg
        self._ffmpeg = None
        if process is None:
            return

        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass

        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def _write_payload(self, payload: bytes) -> bool:
        """Write payload to ffmpeg stdin. Returns True if successful."""
        process = self._ffmpeg
        if process is None or process.stdin is None:
            return False
        try:
            process.stdin.write(payload)
            process.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def _forward(self, payload: bytes) -> None:
        if self._ffmpeg is None or self._ffmpeg.poll() is not None:
            self._start_ffmpeg()

        if self._write_payload(payload):
            return

        self._start_ffmpeg()
        if not self._write_payload(payload):
            # Keep running and retry on next packet.
            pass


def _reset_pipeline_state_locked() -> None:
    global _pipeline, _pipeline_queues
    _pipeline = None
    _pipeline_queues = {}


def _stop_pipeline_locked() -> None:
    global _pipeline
    pipeline = _pipeline
    if pipeline is None:
        _reset_pipeline_state_locked()
        return
    try:
        if pipeline.isRunning():
            pipeline.stop()
    finally:
        _reset_pipeline_state_locked()


def _create_h264_pipeline(
    sockets: Sequence[dai.CameraBoardSocket],
    *,
    width: int,
    height: int,
    fps: int,
    keyframe_interval: int,
) -> tuple[dai.Pipeline, dict[dai.CameraBoardSocket, dai.DataOutputQueue]]:
    pipeline = dai.Pipeline()
    queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
    available_sockets = _pipeline_connected_sockets(pipeline)
    candidate_sockets = _resolve_candidate_sockets(sockets, available_sockets)
    if not candidate_sockets:
        raise ValueError("No cameras available for relay pipeline.")

    for socket in candidate_sockets:
        try:
            cam = pipeline.create(dai.node.Camera).build(socket)
        except Exception as exc:
            print(f"[camera] Skipping unavailable camera socket {socket.name}: {exc}")
            continue
        cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.NV12, fps=fps)

        encoder = pipeline.create(dai.node.VideoEncoder)
        encoder.setDefaultProfilePreset(fps, dai.VideoEncoderProperties.Profile.H264_MAIN)
        try:
            encoder.setKeyframeFrequency(keyframe_interval)
        except Exception:
            # Older DepthAI builds may not expose explicit keyframe control.
            pass
        cam_out.link(encoder.input)
        queues[socket] = encoder.bitstream.createOutputQueue(blocking=False, maxSize=4)

    if not queues:
        requested_names = [socket.name for socket in sockets]
        available_names = [socket.name for socket in available_sockets]
        raise ValueError(
            "No usable camera sockets for relay pipeline "
            f"(requested={requested_names}, available={available_names})."
        )

    return pipeline, queues


def _start_pipeline_locked(
    sockets: Sequence[dai.CameraBoardSocket],
    *,
    width: int,
    height: int,
    fps: int,
    keyframe_interval: int,
) -> dict[dai.CameraBoardSocket, dai.DataOutputQueue]:
    global _pipeline, _pipeline_queues
    sockets_set = set(sockets)

    if (
        _pipeline is not None
        and _pipeline_queues
        and _pipeline.isRunning()
        and set(_pipeline_queues.keys()) == sockets_set
    ):
        return _pipeline_queues

    _stop_pipeline_locked()
    pipeline, queues = _create_h264_pipeline(
        sockets,
        width=width,
        height=height,
        fps=fps,
        keyframe_interval=keyframe_interval,
    )
    pipeline.start()
    _pipeline = pipeline
    _pipeline_queues = queues
    return queues


def ensure_streaming(
    *,
    camera_sockets: Optional[Sequence[dai.CameraBoardSocket]] = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    keyframe_interval: int = DEFAULT_KEYFRAME_INTERVAL,
) -> list[dai.CameraBoardSocket]:
    sockets = (
        order_camera_sockets(camera_sockets)
        if camera_sockets is not None
        else list_camera_sockets()
    )
    if not sockets:
        raise ValueError("No cameras detected for streaming.")

    to_join: list[CameraRelayPublisher] = []
    with _state_lock:
        queues = _start_pipeline_locked(
            sockets,
            width=width,
            height=height,
            fps=fps,
            keyframe_interval=keyframe_interval,
        )
        active_sockets = order_camera_sockets(list(queues.keys()))

        expected = set(active_sockets)
        for socket in list(_publishers.keys()):
            if socket in expected:
                continue
            stale = _publishers.pop(socket)
            stale.stop()
            to_join.append(stale)

        for socket in active_sockets:
            publisher = _publishers.get(socket)
            if publisher is None or not publisher.is_alive():
                if publisher is not None:
                    publisher.stop()
                    to_join.append(publisher)
                publisher = CameraRelayPublisher(
                    camera_socket=socket,
                    queue=queues[socket],
                    fps=fps,
                )
                _publishers[socket] = publisher
                publisher.start()

    for publisher in to_join:
        publisher.join(timeout=2.0)

    return active_sockets


def stop_streaming() -> None:
    with _state_lock:
        publishers = list(_publishers.values())
        _publishers.clear()
        for publisher in publishers:
            publisher.stop()
        _stop_pipeline_locked()

    for publisher in publishers:
        publisher.join(timeout=2.0)
