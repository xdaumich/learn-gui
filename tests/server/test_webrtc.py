import numpy as np

import depthai as dai

import webrtc


class DummyQueue:
    def tryGet(self):  # pragma: no cover - run loop not exercised in these unit tests
        return None


class FakeLogger:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []
        self.timestamps: list[int] = []

    def append(self, frame: np.ndarray, t_ns: int) -> None:
        self.frames.append(frame)
        self.timestamps.append(t_ns)


class FakeRecordingManager:
    def __init__(self, *, active: bool) -> None:
        self._active = active
        self.logger = FakeLogger()
        self.logger_calls: list[tuple[str, int, int]] = []

    def is_active(self) -> bool:
        return self._active

    def get_logger(self, camera_name: str, *, height: int, width: int):
        self.logger_calls.append((camera_name, height, width))
        return self.logger


def test_relay_enabled_parses_boolean_env(monkeypatch) -> None:
    monkeypatch.setenv("WEBRTC_RELAY_ENABLED", "true")
    assert webrtc.relay_enabled() is True
    monkeypatch.setenv("WEBRTC_RELAY_ENABLED", "0")
    assert webrtc.relay_enabled() is False


def test_stream_name_for_socket_lowercases() -> None:
    assert webrtc.stream_name_for_socket(dai.CameraBoardSocket.CAM_A) == "cam_a"
    assert webrtc.stream_name_for_socket(dai.CameraBoardSocket.CAM_B) == "cam_b"


def test_build_ffmpeg_relay_command_for_hevc_passthrough() -> None:
    command = webrtc.build_ffmpeg_relay_command(
        rtsp_url="rtsp://localhost:8554/cam_a",
        fps=30,
        codec="hevc",
    )
    assert command[command.index("-f") + 1] == "hevc"
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[-1] == "rtsp://localhost:8554/cam_a"


def test_build_ffmpeg_relay_command_for_h264_passthrough() -> None:
    command = webrtc.build_ffmpeg_relay_command(
        rtsp_url="rtsp://localhost:8554/cam_b",
        fps=30,
        codec="h264",
    )
    assert command[command.index("-f") + 1] == "h264"
    assert command[command.index("-c:v") + 1] == "copy"


def test_decoder_codec_name_supports_h264_and_hevc() -> None:
    assert webrtc._decoder_codec_name("h264") == "h264"
    assert webrtc._decoder_codec_name("H265") == "hevc"
    assert webrtc._decoder_codec_name("hevc") == "hevc"


def test_camera_relay_publisher_records_decoded_frames() -> None:
    manager = FakeRecordingManager(active=True)
    publisher = webrtc.CameraRelayPublisher(
        camera_socket=dai.CameraBoardSocket.CAM_A,
        queue=DummyQueue(),
        codec="h264",
        recording_manager=manager,
    )
    frames = [
        np.zeros((2, 3, 3), dtype=np.uint8),
        np.full((2, 3, 3), 7, dtype=np.uint8),
    ]

    class FakeDecoder:
        def __init__(self) -> None:
            self.calls = 0

        def decode(self, _payload: bytes):
            self.calls += 1
            return frames

    decoder = FakeDecoder()
    publisher._decoder = decoder
    publisher._record_payload(b"packet", 100)

    assert decoder.calls == 1
    assert manager.logger_calls == [("CAM_A", 2, 3)]
    assert manager.logger.timestamps == [100, 101]
    np.testing.assert_array_equal(manager.logger.frames[0], frames[0])
    np.testing.assert_array_equal(manager.logger.frames[1], frames[1])


def test_camera_relay_publisher_skips_decode_when_recording_inactive() -> None:
    manager = FakeRecordingManager(active=False)
    publisher = webrtc.CameraRelayPublisher(
        camera_socket=dai.CameraBoardSocket.CAM_A,
        queue=DummyQueue(),
        codec="h264",
        recording_manager=manager,
    )

    class FakeDecoder:
        def __init__(self) -> None:
            self.calls = 0

        def decode(self, _payload: bytes):
            self.calls += 1
            return []

    decoder = FakeDecoder()
    publisher._decoder = decoder
    publisher._record_payload(b"packet", 42)

    assert decoder.calls == 0
    assert manager.logger_calls == []
    assert manager.logger.timestamps == []
