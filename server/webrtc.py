"""aiortc peer connection manager."""

from __future__ import annotations

import threading
from typing import Callable, Optional, Sequence, Tuple

import cv2
import depthai as dai
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480

_pipeline_lock = threading.Lock()
_pipeline: Optional[dai.Pipeline] = None
_pipeline_queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
_pipeline_refcount = 0


def list_camera_sockets() -> list[dai.CameraBoardSocket]:
    with dai.Device() as device:
        return list(device.getConnectedCameras())


def _stop_pipeline_locked() -> None:
    global _pipeline, _pipeline_queues, _pipeline_refcount
    if _pipeline is None:
        _pipeline_queues = {}
        _pipeline_refcount = 0
        return
    try:
        if _pipeline.isRunning():
            _pipeline.stop()
    finally:
        _pipeline = None
        _pipeline_queues = {}
        _pipeline_refcount = 0


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
        cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.NV12, fps=fps)
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


class DepthAIVideoTrack(VideoStreamTrack):
    def __init__(self, preview_q: dai.DataOutputQueue) -> None:
        super().__init__()
        self.preview_q = preview_q
        self._released = False

    async def recv(self) -> VideoFrame:
        frame = self.preview_q.get().getCvFrame()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pts, time_base = await self.next_timestamp()
        new_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        new_frame.pts = pts
        new_frame.time_base = time_base
        return new_frame

    def stop(self) -> None:
        if not self._released:
            self._released = True
            _release_pipeline()
        super().stop()


TrackFactory = Callable[[dai.CameraBoardSocket], VideoStreamTrack]


async def create_answer(
    sdp: str,
    sdp_type: str,
    *,
    camera_sockets: Optional[Sequence[dai.CameraBoardSocket]] = None,
    track_factory: Optional[TrackFactory] = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Tuple[RTCSessionDescription, RTCPeerConnection]:
    pc = RTCPeerConnection()
    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)

    sockets = list(camera_sockets) if camera_sockets is not None else list_camera_sockets()
    if not sockets:
        raise ValueError("No cameras detected for streaming.")

    if track_factory is not None:
        for socket in sockets:
            pc.addTrack(track_factory(socket))
    else:
        queues = _start_pipeline(sockets, width=width, height=height)
        for socket in sockets:
            pc.addTrack(DepthAIVideoTrack(queues[socket]))

    await pc.setLocalDescription(await pc.createAnswer())
    return pc.localDescription, pc
