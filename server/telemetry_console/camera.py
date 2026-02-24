"""DepthAI H.264 relay manager for MediaMTX."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence

import av
import depthai as dai
import numpy as np

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 30
DEFAULT_KEYFRAME_INTERVAL = 30
DEFAULT_ENCODER_BITRATE_KBPS = 700
DEFAULT_STREAM_STALL_TIMEOUT_S = 8.0
DEFAULT_RTSP_TEMPLATE = "rtsp://127.0.0.1:8554/{stream_name}"
DEFAULT_FFMPEG_BIN = "ffmpeg"

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


_state_lock = threading.Lock()
_active_stream_targets: list["DeviceStreamTarget"] = []
_active_publishers: dict[str, "CameraRelayPublisher"] = {}
_active_pipelines: dict[str, dai.Pipeline] = {}
_active_devices: dict[str, dai.Device] = {}


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
    # When streams are running, report layout sockets for compatibility helpers.
    with _state_lock:
        if _active_stream_targets:
            count = len(_active_stream_targets)
            return list(CAMERA_LAYOUT_SOCKET_ORDER[:count])

    with dai.Device() as device:
        return order_camera_sockets(list(device.getConnectedCameras()))


def stream_name_for_camera(camera_name: str) -> str:
    return camera_name.lower()


def stream_name_for_socket(socket: dai.CameraBoardSocket) -> str:
    return stream_name_for_camera(socket.name)


def stream_name_for_slot(slot: str) -> str:
    return slot.lower()


def _pipeline_connected_sockets(pipeline: dai.Pipeline) -> list[dai.CameraBoardSocket]:
    # Retained for compatibility with older camera tests that inspect this helper.
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


def _h264_contains_idr(payload: bytes) -> bool:
    """Return True if payload contains an IDR, SPS, or PPS NAL unit."""
    i = 0
    while i < len(payload) - 3:
        if payload[i : i + 4] == b"\x00\x00\x00\x01":
            nal_start = i + 4
            step = 4
        elif payload[i : i + 3] == b"\x00\x00\x01":
            nal_start = i + 3
            step = 3
        else:
            i += 1
            continue
        if nal_start < len(payload):
            nal_type = payload[nal_start] & 0x1F
            if nal_type in (5, 7, 8):  # IDR, SPS, PPS
                return True
        i += step
    return False


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
        stream_name: str,
        queue: dai.MessageQueue,
        fps: int,
    ) -> None:
        super().__init__(daemon=True, name=f"relay-{stream_name}")
        self._stream_name = stream_name
        self._queue = queue
        self._fps = max(1, fps)
        self._frame_interval_ns = int(1e9 / self._fps)
        self._stop_event = threading.Event()
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self._rtsp_url = _rtsp_url_for_stream(stream_name)
        self._last_payload_monotonic_s = time.monotonic()
        self._needs_keyframe = True  # require IDR before writing to a fresh ffmpeg

    def run(self) -> None:
        self._start_ffmpeg()
        self._needs_keyframe = True
        while not self._stop_event.is_set():
            payload = self._drain_latest_payload()
            if payload is None:
                time.sleep(0.002)
                continue
            self._needs_keyframe = False
            self._last_payload_monotonic_s = time.monotonic()
            self._forward(payload)
        self._close_ffmpeg()

    def stop(self) -> None:
        self._stop_event.set()

    def is_healthy(self, *, max_silence_s: float) -> bool:
        if not self.is_alive():
            return False
        return (time.monotonic() - self._last_payload_monotonic_s) <= max(0.5, max_silence_s)

    def _start_ffmpeg(self) -> None:
        self._close_ffmpeg()
        command = build_ffmpeg_command(rtsp_url=self._rtsp_url, fps=self._fps)
        self._ffmpeg = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        if self._ffmpeg.stdin is not None:
            try:
                os.set_blocking(self._ffmpeg.stdin.fileno(), False)
            except Exception:
                pass

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

    def _drain_latest_payload(self) -> bytes | None:
        try:
            packets = self._queue.tryGetAll()
        except Exception:
            packets = []
        if not packets:
            try:
                packet = self._queue.tryGet()
            except Exception:
                return None
            if packet is None:
                return None
            packets = [packet]

        if self._needs_keyframe:
            # Scan packets in arrival order for the first IDR-containing packet.
            # Discards leading P-frames that would crash a freshly-started ffmpeg.
            for pkt in packets:
                try:
                    data = bytes(pkt.getData())
                except Exception:
                    continue
                if data and _h264_contains_idr(data):
                    return data
            return None  # no IDR yet — keep waiting

        packet = packets[-1]
        try:
            payload = bytes(packet.getData())
        except Exception:
            return None
        if not payload:
            return None
        return payload

    def _write_payload(self, payload: bytes) -> bool:
        """Write payload to ffmpeg stdin. Returns False when restart is needed."""
        process = self._ffmpeg
        if process is None or process.stdin is None:
            return False
        try:
            view = memoryview(payload)
            while view:
                written = os.write(process.stdin.fileno(), view)
                if written <= 0:
                    return True
                view = view[written:]
            return True
        except BlockingIOError:
            # Pipe full: drop this frame to keep queue draining healthy.
            return True
        except (BrokenPipeError, OSError):
            return False

    def _forward(self, payload: bytes) -> None:
        if self._ffmpeg is None or self._ffmpeg.poll() is not None:
            self._start_ffmpeg()
            self._needs_keyframe = True
            return  # discard current packet; next iteration waits for IDR

        if self._write_payload(payload):
            return

        self._start_ffmpeg()
        self._needs_keyframe = True
        # discard current packet; next iteration waits for IDR


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
) -> list[DeviceStreamTarget]:
    # Step 1: preserve currently active targets (streams already running on BOOTED devices).
    with _state_lock:
        existing_targets: list[DeviceStreamTarget] = list(_active_stream_targets)

    existing_device_ids = {t.device_id for t in existing_targets}
    existing_slot_names = {t.stream_name for t in existing_targets}

    # Step 2: discover freshly available (UNBOOTED) devices not already in active streams.
    all_profiles = _discover_device_profiles()
    new_profiles = [p for p in all_profiles if p.device_id not in existing_device_ids]

    if not existing_targets and not new_profiles:
        return []

    # Step 3: apply OAK-D center-slot ordering to the new profiles.
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

    # Step 4: build target list — existing slots preserved, empty slots filled in order.
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


def list_stream_names() -> list[str]:
    with _state_lock:
        return [target.stream_name for target in _active_stream_targets]


def list_stream_targets() -> list[DeviceStreamTarget]:
    with _state_lock:
        return list(_active_stream_targets)


def _build_h264_pipeline(
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
    encoder.setDefaultProfilePreset(fps, dai.VideoEncoderProperties.Profile.H264_MAIN)
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
    queue = encoder.out.createOutputQueue(maxSize=4, blocking=False)
    return pipeline, queue


def _close_and_clear_streams() -> tuple[
    list[CameraRelayPublisher], list[dai.Pipeline], list[dai.Device]
]:
    to_join: list[CameraRelayPublisher] = []
    to_stop: list[dai.Pipeline] = []
    to_close: list[dai.Device] = []
    for stream_name, publisher in list(_active_publishers.items()):
        publisher.stop()
        to_join.append(publisher)
        _active_publishers.pop(stream_name, None)

    for stream_name, pipeline in list(_active_pipelines.items()):
        to_stop.append(pipeline)
        _active_pipelines.pop(stream_name, None)

    for stream_name, device in list(_active_devices.items()):
        to_close.append(device)
        _active_devices.pop(stream_name, None)

    return to_join, to_stop, to_close


def _start_stream_for_target(
    target: DeviceStreamTarget,
    *,
    width: int,
    height: int,
    fps: int,
    keyframe_interval: int,
) -> None:
    try:
        device = dai.Device(target.device_info)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to start camera stream for {target.stream_name}: {exc}"
        ) from exc

    try:
        pipeline, queue = _build_h264_pipeline(
            device=device,
            width=width,
            height=height,
            fps=fps,
            keyframe_interval=keyframe_interval,
        )
        pipeline.start()

        publisher = CameraRelayPublisher(stream_name=target.stream_name, queue=queue, fps=fps)
        publisher.start()
    except Exception:
        try:
            device.close()
        except Exception:
            pass
        raise

    _active_publishers[target.stream_name] = publisher
    _active_pipelines[target.stream_name] = pipeline
    _active_devices[target.stream_name] = device


def ensure_streaming(
    *,
    camera_sockets: Optional[Sequence[dai.CameraBoardSocket]] = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    keyframe_interval: int = DEFAULT_KEYFRAME_INTERVAL,
) -> list[str]:
    targets = _resolve_target_streams(camera_sockets)
    if not targets:
        raise ValueError("No cameras detected for streaming.")

    to_join: list[CameraRelayPublisher] = []
    to_stop: list[dai.Pipeline] = []
    to_close: list[dai.Device] = []
    try:
        stall_timeout_s = float(
            os.environ.get("CAMERA_STREAM_STALL_TIMEOUT_S", DEFAULT_STREAM_STALL_TIMEOUT_S)
        )
    except (TypeError, ValueError):
        stall_timeout_s = DEFAULT_STREAM_STALL_TIMEOUT_S

    target_names = {target.stream_name for target in targets}
    started_targets: list[DeviceStreamTarget] = []

    with _state_lock:
        current_names = set(_active_publishers.keys())
        for stale_name in current_names - target_names:
            stale_publisher = _active_publishers.pop(stale_name, None)
            if stale_publisher is not None:
                stale_publisher.stop()
                to_join.append(stale_publisher)

            stale_pipeline = _active_pipelines.pop(stale_name, None)
            if stale_pipeline is not None:
                to_stop.append(stale_pipeline)

            stale_device = _active_devices.pop(stale_name, None)
            if stale_device is not None:
                to_close.append(stale_device)

        _active_stream_targets.clear()
        for target in targets:
            existing = _active_publishers.get(target.stream_name)
            if existing is not None and existing.is_healthy(max_silence_s=stall_timeout_s):
                started_targets.append(target)
                continue

            if existing is not None:
                existing.stop()
                to_join.append(existing)
                _active_publishers.pop(target.stream_name, None)
            existing_pipeline = _active_pipelines.pop(target.stream_name, None)
            if existing_pipeline is not None:
                to_stop.append(existing_pipeline)
            existing_device = _active_devices.pop(target.stream_name, None)
            if existing_device is not None:
                to_close.append(existing_device)

            try:
                _start_stream_for_target(
                    target,
                    width=width,
                    height=height,
                    fps=fps,
                    keyframe_interval=keyframe_interval,
                )
                started_targets.append(target)
            except Exception:
                # Keep partial streaming alive if at least one device starts.
                continue

        _active_stream_targets.extend(started_targets)

    for publisher in to_join:
        publisher.join(timeout=2.0)
    for pipeline in to_stop:
        try:
            pipeline.stop()
        except Exception:
            pass
    for device in to_close:
        try:
            device.close()
        except Exception:
            pass

    if not started_targets:
        with _state_lock:
            _active_stream_targets.clear()
        raise RuntimeError("Failed to start any camera streams.")
    return [target.stream_name for target in started_targets]


def stop_streaming() -> None:
    to_join: list[CameraRelayPublisher] = []
    to_stop: list[dai.Pipeline] = []
    to_close: list[dai.Device] = []
    with _state_lock:
        to_join, to_stop, to_close = _close_and_clear_streams()
        _active_stream_targets.clear()

    for publisher in to_join:
        publisher.join(timeout=2.0)
    for pipeline in to_stop:
        try:
            pipeline.stop()
        except Exception:
            pass
    for device in to_close:
        try:
            device.close()
        except Exception:
            pass
