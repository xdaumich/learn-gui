"""DepthAI camera discovery and H.264 pipeline builder."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional, Sequence

import depthai as dai

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 30
DEFAULT_KEYFRAME_INTERVAL = 30
DEFAULT_ENCODER_BITRATE_KBPS = 700

# Order used for the 3-stream layout in UI.
CAMERA_STREAM_LAYOUT = ("left", "center", "right")

# Legacy socket order retained for compatibility with older naming tests/utilities.
CAMERA_LAYOUT_SOCKET_ORDER = (
    dai.CameraBoardSocket.CAM_B,  # left
    dai.CameraBoardSocket.CAM_A,  # center
    dai.CameraBoardSocket.CAM_C,  # right
)
_CAMERA_SOCKET_ORDER_INDEX = {
    socket: index for index, socket in enumerate(CAMERA_LAYOUT_SOCKET_ORDER)
}

# Prefer OAK-D model for the center slot so RGB from the dedicated stereo rig is shown there.
_OAK_D_PREFIX = "OAK-D"


@dataclass(frozen=True)
class DeviceProfile:
    device_info: dai.DeviceInfo
    device_name: str
    device_id: str

    @property
    def is_oak_d(self) -> bool:
        return self.device_name.upper().startswith(_OAK_D_PREFIX)


@dataclass(frozen=True)
class DeviceStreamTarget:
    stream_name: str
    device_info: dai.DeviceInfo
    device_name: str
    device_id: str


def order_camera_sockets(
    sockets: Sequence[dai.CameraBoardSocket],
) -> list[dai.CameraBoardSocket]:
    """Order sockets to match physical layout: left, center, right."""
    unique_sockets = list(dict.fromkeys(sockets))
    fallback_index = len(_CAMERA_SOCKET_ORDER_INDEX)
    return sorted(
        unique_sockets,
        key=lambda socket: (_CAMERA_SOCKET_ORDER_INDEX.get(socket, fallback_index), socket.name),
    )


def list_camera_sockets() -> list[dai.CameraBoardSocket]:
    with dai.Device() as device:
        return order_camera_sockets(list(device.getConnectedCameras()))


def stream_name_for_camera(camera_name: str) -> str:
    return camera_name.lower()


def stream_name_for_socket(socket: dai.CameraBoardSocket) -> str:
    return stream_name_for_camera(socket.name)


def stream_name_for_slot(slot: str) -> str:
    return slot.lower()


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


def _get_device_profile(info: dai.DeviceInfo) -> DeviceProfile:
    device_id = str(getattr(info, "deviceId", "") or "")
    if not device_id:
        get_device_id = getattr(info, "getDeviceId", None)
        if callable(get_device_id):
            try:
                device_id = str(get_device_id())
            except Exception:
                device_id = ""
    if not device_id:
        device_id = "unknown"

    raw_name = str(getattr(info, "name", "") or "")
    # Unbooted DeviceInfo.name is typically a USB path, not model metadata.
    device_name = raw_name if raw_name.upper().startswith("OAK-") else "OAK"
    return DeviceProfile(
        device_info=info,
        device_name=device_name,
        device_id=device_id,
    )


def _discover_device_profiles() -> list[DeviceProfile]:
    profiles: list[DeviceProfile] = []
    for info in dai.Device.getAllAvailableDevices():
        try:
            profiles.append(_get_device_profile(info))
        except Exception:
            # Best-effort scanning: skip transient/unready descriptors.
            continue

    return sorted(
        profiles,
        key=lambda profile: (not profile.is_oak_d, profile.device_name, profile.device_id),
    )


def _resolve_target_streams(
    requested: Optional[Sequence[dai.CameraBoardSocket]],
    *,
    existing_targets: list[DeviceStreamTarget] | None = None,
) -> list[DeviceStreamTarget]:
    if existing_targets is None:
        existing_targets = []

    existing_device_ids = {t.device_id for t in existing_targets}

    # Discover freshly available (UNBOOTED) devices not already in active streams.
    all_profiles = _discover_device_profiles()
    new_profiles = [p for p in all_profiles if p.device_id not in existing_device_ids]

    if not existing_targets and not new_profiles:
        return []

    # Apply OAK-D center-slot ordering to the new profiles.
    oak_d = [p for p in new_profiles if p.is_oak_d]
    other = [p for p in new_profiles if not p.is_oak_d]
    if oak_d:
        if len(other) >= 2:
            ordered_new = [other[0], oak_d[0], other[1]]
        elif len(other) == 1:
            ordered_new = [other[0], oak_d[0]]
        else:
            ordered_new = list(oak_d)
    else:
        ordered_new = list(new_profiles)

    # Build target list — existing slots preserved, empty slots filled in order.
    active_by_slot = {t.stream_name: t for t in existing_targets}
    new_iter = iter(ordered_new)
    targets: list[DeviceStreamTarget] = []
    for slot in CAMERA_STREAM_LAYOUT:
        if slot in active_by_slot:
            targets.append(active_by_slot[slot])
        else:
            profile = next(new_iter, None)
            if profile is not None:
                targets.append(
                    DeviceStreamTarget(
                        stream_name=slot,
                        device_info=profile.device_info,
                        device_name=profile.device_name,
                        device_id=profile.device_id,
                    )
                )

    if requested is not None:
        requested_count = max(0, len(order_camera_sockets(requested)))
        targets = targets[:requested_count]

    return targets


def build_h264_pipeline(
    *,
    device: dai.Device,
    width: int,
    height: int,
    fps: int,
    keyframe_interval: int,
) -> tuple[dai.Pipeline, dai.MessageQueue]:
    pipeline = dai.Pipeline(device)

    cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.NV12, fps=fps)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(fps, dai.VideoEncoderProperties.Profile.H264_BASELINE)
    try:
        encoder.setKeyframeFrequency(keyframe_interval)
    except Exception:
        pass
    try:
        bitrate_kbps = int(
            os.environ.get("CAMERA_ENCODER_BITRATE_KBPS", DEFAULT_ENCODER_BITRATE_KBPS)
        )
        encoder.setRateControlMode(dai.VideoEncoderProperties.RateControlMode.CBR)
        encoder.setBitrateKbps(max(150, bitrate_kbps))
        encoder.setNumBFrames(0)
    except Exception:
        pass

    cam_out.link(encoder.input)
    queue = encoder.out.createOutputQueue(maxSize=1, blocking=False)
    return pipeline, queue


# Keep old private name as alias so existing callers (webrtc_sessions.py) work during migration.
_build_h264_pipeline = build_h264_pipeline
