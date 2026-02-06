"""aiortc peer connection manager."""

from __future__ import annotations

import threading
from typing import Callable, Optional, Tuple

import cv2
import depthai as dai
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480

_pipeline_lock = threading.Lock()
_pipeline: Optional[dai.Pipeline] = None


def _stop_pipeline() -> None:
    global _pipeline
    if _pipeline is None:
        return
    try:
        if _pipeline.isRunning():
            _pipeline.stop()
    finally:
        _pipeline = None


def _create_rgb_pipeline(
    width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT
) -> tuple[dai.Pipeline, dai.DataOutputQueue]:
    pipeline = dai.Pipeline()
    cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)

    try:
        platform = pipeline.getDefaultDevice().getPlatformAsString()
    except Exception:
        platform = ""
    fps = 30 if platform == "RVC4" else 15

    cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.NV12, fps=fps)
    preview_q = cam_out.createOutputQueue(blocking=False, maxSize=4)
    return pipeline, preview_q


def _start_pipeline(
    width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT
) -> tuple[dai.Pipeline, dai.DataOutputQueue]:
    global _pipeline
    with _pipeline_lock:
        _stop_pipeline()
        pipeline, preview_q = _create_rgb_pipeline(width=width, height=height)
        pipeline.start()
        _pipeline = pipeline
        return pipeline, preview_q


class DepthAIVideoTrack(VideoStreamTrack):
    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> None:
        super().__init__()
        self.pipeline, self.preview_q = _start_pipeline(width=width, height=height)

    async def recv(self) -> VideoFrame:
        frame = self.preview_q.get().getCvFrame()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pts, time_base = await self.next_timestamp()
        new_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        new_frame.pts = pts
        new_frame.time_base = time_base
        return new_frame

    def stop(self) -> None:
        _stop_pipeline()
        super().stop()


TrackFactory = Callable[[], VideoStreamTrack]


async def create_answer(
    sdp: str,
    sdp_type: str,
    *,
    track_factory: Optional[TrackFactory] = None,
) -> Tuple[RTCSessionDescription, RTCPeerConnection]:
    pc = RTCPeerConnection()
    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)

    track = track_factory() if track_factory is not None else DepthAIVideoTrack()
    pc.addTrack(track)

    await pc.setLocalDescription(await pc.createAnswer())
    return pc.localDescription, pc
