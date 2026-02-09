"""aiortc peer connection manager."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Sequence, Tuple

import depthai as dai
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

from data_log import RecordingManager

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480

_pipeline_lock = threading.Lock()
_pipeline: Optional[dai.Pipeline] = None
_pipeline_queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
_pipeline_refcount = 0


def list_camera_sockets() -> list[dai.CameraBoardSocket]:
    # When the streaming pipeline is active, avoid opening a second connection to the device.
    # On some platforms / firmware states this can fail with X_LINK_* errors.
    with _pipeline_lock:
        if _pipeline is not None and _pipeline_queues:
            return list(_pipeline_queues.keys())

    with dai.Device() as device:
        return list(device.getConnectedCameras())


def _reset_pipeline_state_locked() -> None:
    global _pipeline, _pipeline_queues, _pipeline_refcount
    _pipeline = None
    _pipeline_queues = {}
    _pipeline_refcount = 0


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


def _stop_pipeline() -> None:
    with _pipeline_lock:
        _stop_pipeline_locked()


def _create_rgb_pipeline(
    sockets: Sequence[dai.CameraBoardSocket],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> tuple[dai.Pipeline, dict[dai.CameraBoardSocket, dai.DataOutputQueue]]:
    pipeline = dai.Pipeline()

    try:
        platform = pipeline.getDefaultDevice().getPlatformAsString()
    except Exception:
        platform = ""
    fps = 30 if platform == "RVC4" else 15

    queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
    for socket in sockets:
        cam = pipeline.create(dai.node.Camera).build(socket)
        # Ask the device for interleaved RGB to avoid importing OpenCV (cv2) in the server process.
        cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.RGB888i, fps=fps)
        queues[socket] = cam_out.createOutputQueue(blocking=False, maxSize=4)

    return pipeline, queues


def _start_pipeline(
    sockets: Sequence[dai.CameraBoardSocket],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> dict[dai.CameraBoardSocket, dai.DataOutputQueue]:
    global _pipeline, _pipeline_queues, _pipeline_refcount
    if not sockets:
        raise ValueError("No cameras detected for streaming.")
    with _pipeline_lock:
        sockets_set = set(sockets)
        # If the pipeline is already running for the same set of sockets, reuse it and
        # bump the refcount for the additional tracks we're about to create.
        if (
            _pipeline is not None
            and _pipeline_queues
            and _pipeline.isRunning()
            and set(_pipeline_queues.keys()) == sockets_set
        ):
            _pipeline_refcount += len(sockets)
            return _pipeline_queues

        _stop_pipeline_locked()
        pipeline, queues = _create_rgb_pipeline(sockets, width=width, height=height)
        pipeline.start()
        _pipeline = pipeline
        _pipeline_queues = queues
        _pipeline_refcount = len(queues)
        return queues


def _release_pipeline() -> None:
    global _pipeline_refcount
    with _pipeline_lock:
        if _pipeline_refcount <= 0:
            return
        _pipeline_refcount -= 1
        if _pipeline_refcount == 0:
            _stop_pipeline_locked()


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


class DepthAIVideoTrack(VideoStreamTrack):
    def __init__(
        self,
        frame_queue: dai.DataOutputQueue,
        *,
        camera_socket: dai.CameraBoardSocket,
        recording_manager: RecordingManager | None = None,
    ) -> None:
        super().__init__()
        self._frame_queue = frame_queue
        self._camera_socket = camera_socket
        self._recording_manager = recording_manager
        self._pipeline_released = False
        self._logging_error: Exception | None = None

    async def recv(self) -> VideoFrame:
        img = self._frame_queue.get()
        frame = img.getFrame().reshape((img.getHeight(), img.getWidth(), 3))
        t_ns = _timestamp_ns(img)

        if self._recording_manager is not None and self._logging_error is None:
            try:
                logger = self._recording_manager.get_logger(
                    self._camera_socket.name,
                    height=frame.shape[0],
                    width=frame.shape[1],
                )
                if logger is not None:
                    logger.append(frame, t_ns)
            except Exception as exc:
                self._logging_error = exc
                print(f"[data_log] Failed to log frame: {exc}")

        pts, time_base = await self.next_timestamp()
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self) -> None:
        if not self._pipeline_released:
            self._pipeline_released = True
            _release_pipeline()
        super().stop()


TrackFactory = Callable[[dai.CameraBoardSocket], VideoStreamTrack]


async def create_answer(
    sdp: str,
    sdp_type: str,
    *,
    camera_sockets: Optional[Sequence[dai.CameraBoardSocket]] = None,
    track_factory: Optional[TrackFactory] = None,
    recording_manager: RecordingManager | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Tuple[RTCSessionDescription, RTCPeerConnection]:
    pc = RTCPeerConnection()
    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)

    sockets = list(camera_sockets) if camera_sockets is not None else list_camera_sockets()
    if not sockets:
        raise ValueError("No cameras detected for streaming.")

    if track_factory is None:
        queues = _start_pipeline(sockets, width=width, height=height)

        def track_factory(socket: dai.CameraBoardSocket) -> VideoStreamTrack:
            return DepthAIVideoTrack(
                queues[socket],
                camera_socket=socket,
                recording_manager=recording_manager,
            )

    for socket in sockets:
        pc.addTrack(track_factory(socket))

    await pc.setLocalDescription(await pc.createAnswer())
    return pc.localDescription, pc
