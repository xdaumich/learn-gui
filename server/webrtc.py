"""DepthAI-to-MediaMTX relay manager with optional recording decode tap."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Optional, Sequence

import depthai as dai
import av

from data_log import RecordingManager

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_RELAY_FPS = 30
DEFAULT_RELAY_KEYFRAME_INTERVAL = 30
DEFAULT_MEDIAMTX_RTSP_TEMPLATE = "rtsp://127.0.0.1:8554/{stream_name}"
DEFAULT_FFMPEG_BIN = "ffmpeg"
DEFAULT_RELAY_CODEC = "h264"

_relay_lock = threading.Lock()
_relay_pipeline: Optional[dai.Pipeline] = None
_relay_queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
_relay_publishers: dict[dai.CameraBoardSocket, "CameraRelayPublisher"] = {}
_relay_codec: str | None = None


def list_camera_sockets() -> list[dai.CameraBoardSocket]:
    # When relay pipeline is active, avoid opening a second connection to the device.
    # On some platforms / firmware states this can fail with X_LINK_* errors.
    with _relay_lock:
        if _relay_pipeline is not None and _relay_queues:
            return list(_relay_queues.keys())

    with dai.Device() as device:
        return list(device.getConnectedCameras())


def relay_enabled() -> bool:
    """Return whether relay mode is enabled via env flag."""
    value = os.environ.get("WEBRTC_RELAY_ENABLED", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def stream_name_for_camera(camera_name: str) -> str:
    """Normalize camera name into a stable relay stream path."""
    return camera_name.lower()


def stream_name_for_socket(socket: dai.CameraBoardSocket) -> str:
    return stream_name_for_camera(socket.name)


def _normalize_codec(codec: str) -> str:
    return codec.strip().lower()


def _rtsp_url_for_stream(stream_name: str) -> str:
    template = os.environ.get("MEDIAMTX_RTSP_TEMPLATE", DEFAULT_MEDIAMTX_RTSP_TEMPLATE)
    return template.format(stream_name=stream_name)


def build_ffmpeg_relay_command(*, rtsp_url: str, fps: int, codec: str = DEFAULT_RELAY_CODEC) -> list[str]:
    """Build ffmpeg command for push-relay passthrough."""
    ffmpeg_bin = os.environ.get("FFMPEG_BIN", DEFAULT_FFMPEG_BIN)
    input_format = "hevc" if _normalize_codec(codec) in {"hevc", "h265"} else "h264"
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-fflags",
        "+genpts",
        "-f",
        input_format,
        "-framerate",
        str(max(1, fps)),
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


def _start_ffmpeg_relay_process(*, stream_name: str, fps: int, codec: str) -> subprocess.Popen[bytes]:
    command = build_ffmpeg_relay_command(
        rtsp_url=_rtsp_url_for_stream(stream_name),
        fps=fps,
        codec=codec,
    )
    return subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _close_ffmpeg_process(process: subprocess.Popen[bytes] | None) -> None:
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


def _reset_relay_state_locked() -> None:
    global _relay_pipeline, _relay_queues, _relay_codec
    _relay_pipeline = None
    _relay_queues = {}
    _relay_codec = None


def _stop_relay_pipeline_locked() -> None:
    global _relay_pipeline
    pipeline = _relay_pipeline
    if pipeline is None:
        _reset_relay_state_locked()
        return
    try:
        if pipeline.isRunning():
            pipeline.stop()
    finally:
        _reset_relay_state_locked()


def _encoder_profile(codec: str) -> dai.VideoEncoderProperties.Profile:
    profile_type = dai.VideoEncoderProperties.Profile
    if _normalize_codec(codec) in {"hevc", "h265"}:
        hevc_profile = getattr(profile_type, "H265_MAIN", None)
        if hevc_profile is not None:
            return hevc_profile
        hevc_profile = getattr(profile_type, "HEVC_MAIN", None)
        if hevc_profile is not None:
            return hevc_profile
    # Fallback keeps the scaffold import-safe on older SDK variants.
    return profile_type.H264_MAIN


def _create_encoded_pipeline(
    sockets: Sequence[dai.CameraBoardSocket],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_RELAY_FPS,
    keyframe_interval: int = DEFAULT_RELAY_KEYFRAME_INTERVAL,
    codec: str = DEFAULT_RELAY_CODEC,
) -> tuple[dai.Pipeline, dict[dai.CameraBoardSocket, dai.DataOutputQueue]]:
    """Relay pipeline: produce compressed bitstreams directly from device."""
    pipeline = dai.Pipeline()
    queues: dict[dai.CameraBoardSocket, dai.DataOutputQueue] = {}
    safe_fps = max(1, fps)
    safe_keyframe_interval = max(1, keyframe_interval)

    for socket in sockets:
        cam = pipeline.create(dai.node.Camera).build(socket)
        cam_out = cam.requestOutput((width, height), dai.ImgFrame.Type.NV12, fps=safe_fps)
        encoder = pipeline.create(dai.node.VideoEncoder)
        encoder.setDefaultProfilePreset(safe_fps, _encoder_profile(codec))
        try:
            encoder.setKeyframeFrequency(safe_keyframe_interval)
        except Exception:
            # Some DepthAI builds do not expose explicit keyframe controls.
            pass
        cam_out.link(encoder.input)
        queues[socket] = encoder.bitstream.createOutputQueue(blocking=False, maxSize=4)

    return pipeline, queues


def _start_relay_pipeline_locked(
    sockets: Sequence[dai.CameraBoardSocket],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_RELAY_FPS,
    keyframe_interval: int = DEFAULT_RELAY_KEYFRAME_INTERVAL,
    codec: str = DEFAULT_RELAY_CODEC,
) -> dict[dai.CameraBoardSocket, dai.DataOutputQueue]:
    global _relay_pipeline, _relay_queues, _relay_codec
    if not sockets:
        raise ValueError("No cameras detected for relay streaming.")

    codec_norm = _normalize_codec(codec)
    sockets_set = set(sockets)
    if (
        _relay_pipeline is not None
        and _relay_queues
        and _relay_pipeline.isRunning()
        and _relay_codec == codec_norm
        and set(_relay_queues.keys()) == sockets_set
    ):
        return _relay_queues

    _stop_relay_pipeline_locked()
    pipeline, queues = _create_encoded_pipeline(
        sockets,
        width=width,
        height=height,
        fps=fps,
        keyframe_interval=keyframe_interval,
        codec=codec_norm,
    )
    pipeline.start()
    _relay_pipeline = pipeline
    _relay_queues = queues
    _relay_codec = codec_norm
    return queues


def _timestamp_ns(packet: object) -> int:
    for getter in ("getTimestampDevice", "getTimestamp"):
        fn = getattr(packet, getter, None)
        if not callable(fn):
            continue
        try:
            ts = fn()
            if ts is not None:
                return int(ts.total_seconds() * 1e9)
        except Exception:
            continue
    return time.time_ns()


def _decoder_codec_name(codec: str) -> str:
    if _normalize_codec(codec) in {"hevc", "h265"}:
        return "hevc"
    return "h264"


class EncodedFrameDecoder:
    """Decode encoded camera packets into RGB frames for recording."""

    def __init__(self, codec: str) -> None:
        self._context = av.CodecContext.create(_decoder_codec_name(codec), "r")

    def decode(self, payload: bytes) -> list[object]:
        packet = av.Packet(payload)
        return [frame.to_ndarray(format="rgb24") for frame in self._context.decode(packet)]


class CameraRelayPublisher(threading.Thread):
    """Publish encoded camera packets from DepthAI into MediaMTX via ffmpeg."""

    def __init__(
        self,
        *,
        camera_socket: dai.CameraBoardSocket,
        queue: dai.DataOutputQueue,
        fps: int = DEFAULT_RELAY_FPS,
        codec: str = DEFAULT_RELAY_CODEC,
        recording_manager: RecordingManager | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"relay-{camera_socket.name.lower()}")
        self._camera_socket = camera_socket
        self._queue = queue
        self._fps = max(1, fps)
        self._codec = codec
        self._recording_manager = recording_manager
        self._stop_event = threading.Event()
        self._first_packet_event = threading.Event()
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self._decoder = EncodedFrameDecoder(codec) if recording_manager is not None else None
        self._recording_error: Exception | None = None

    def stop(self) -> None:
        self._stop_event.set()

    def wait_until_ready(self, timeout: float) -> bool:
        return self._first_packet_event.wait(timeout=max(0.0, timeout))

    def run(self) -> None:
        self._start_ffmpeg()
        try:
            while not self._stop_event.is_set():
                packet = self._queue.tryGet()
                if packet is None:
                    time.sleep(0.002)
                    continue
                payload = bytes(packet.getData())
                if not payload:
                    continue
                self._forward(payload)
                self._record_payload(payload, _timestamp_ns(packet))
                self._first_packet_event.set()
        finally:
            self._close_ffmpeg()

    def _start_ffmpeg(self) -> None:
        self._close_ffmpeg()
        self._ffmpeg = _start_ffmpeg_relay_process(
            stream_name=stream_name_for_socket(self._camera_socket),
            fps=self._fps,
            codec=self._codec,
        )

    def _close_ffmpeg(self) -> None:
        process = self._ffmpeg
        self._ffmpeg = None
        _close_ffmpeg_process(process)

    def _try_write(self, payload: bytes) -> bool:
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
        if self._try_write(payload):
            return
        self._start_ffmpeg()
        self._try_write(payload)

    def _record_payload(self, payload: bytes, t_ns: int) -> None:
        manager = self._recording_manager
        decoder = self._decoder
        if manager is None or decoder is None or self._recording_error is not None:
            return
        if not manager.is_active():
            return

        try:
            frames = decoder.decode(payload)
        except Exception as exc:
            self._recording_error = exc
            print(f"[data_log] Failed to decode relay packet for recording: {exc}")
            return
        if not frames:
            return

        first_frame = frames[0]
        logger = manager.get_logger(
            self._camera_socket.name,
            height=first_frame.shape[0],
            width=first_frame.shape[1],
        )
        if logger is None:
            return

        for index, frame in enumerate(frames):
            logger.append(frame, t_ns + index)


def ensure_streaming(
    *,
    camera_sockets: Optional[Sequence[dai.CameraBoardSocket]] = None,
    recording_manager: RecordingManager | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_RELAY_FPS,
    keyframe_interval: int = DEFAULT_RELAY_KEYFRAME_INTERVAL,
    codec: str = DEFAULT_RELAY_CODEC,
) -> list[dai.CameraBoardSocket]:
    """Ensure relay pipeline and ffmpeg publishers are running for all cameras."""
    sockets = list(camera_sockets) if camera_sockets is not None else list_camera_sockets()
    if not sockets:
        raise ValueError("No cameras detected for relay streaming.")

    stale_publishers: list[CameraRelayPublisher] = []
    active_publishers: list[CameraRelayPublisher] = []
    codec_norm = _normalize_codec(codec)
    with _relay_lock:
        queues = _start_relay_pipeline_locked(
            sockets,
            width=width,
            height=height,
            fps=fps,
            keyframe_interval=keyframe_interval,
            codec=codec_norm,
        )
        active_sockets = list(queues.keys())
        active_set = set(active_sockets)

        for socket in list(_relay_publishers.keys()):
            if socket in active_set:
                continue
            publisher = _relay_publishers.pop(socket)
            publisher.stop()
            stale_publishers.append(publisher)

        for socket in active_sockets:
            publisher = _relay_publishers.get(socket)
            if publisher is None or not publisher.is_alive():
                if publisher is not None:
                    publisher.stop()
                    stale_publishers.append(publisher)
                publisher = CameraRelayPublisher(
                    camera_socket=socket,
                    queue=queues[socket],
                    fps=fps,
                    codec=codec_norm,
                    recording_manager=recording_manager,
                )
                _relay_publishers[socket] = publisher
                publisher.start()
            active_publishers.append(publisher)

    for publisher in stale_publishers:
        publisher.join(timeout=2.0)
    # Give relay publishers a brief window to emit first packets before clients connect.
    deadline = time.monotonic() + 2.5
    for publisher in active_publishers:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining == 0.0:
            break
        publisher.wait_until_ready(timeout=remaining)

    return active_sockets


def stop_streaming() -> None:
    """Stop relay publishers and release relay pipeline."""
    with _relay_lock:
        publishers = list(_relay_publishers.values())
        _relay_publishers.clear()
        for publisher in publishers:
            publisher.stop()
        _stop_relay_pipeline_locked()
    for publisher in publishers:
        publisher.join(timeout=2.0)
