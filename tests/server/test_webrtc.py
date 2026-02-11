import depthai as dai
import numpy as np

import webrtc


def test_stream_name_for_socket_lowercases() -> None:
    assert webrtc.stream_name_for_socket(dai.CameraBoardSocket.CAM_A) == "cam_a"
    assert webrtc.stream_name_for_socket(dai.CameraBoardSocket.CAM_B) == "cam_b"


def test_order_camera_sockets_matches_hardware_layout() -> None:
    sockets = [
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_C,
        dai.CameraBoardSocket.CAM_B,
    ]
    assert webrtc.order_camera_sockets(sockets) == [
        dai.CameraBoardSocket.CAM_B,
        dai.CameraBoardSocket.CAM_A,
        dai.CameraBoardSocket.CAM_C,
    ]


def test_resolve_candidate_sockets_prefers_requested_available_intersection() -> None:
    requested = [dai.CameraBoardSocket.CAM_A, dai.CameraBoardSocket.CAM_C]
    available = [dai.CameraBoardSocket.CAM_A, dai.CameraBoardSocket.CAM_B]
    assert webrtc._resolve_candidate_sockets(requested, available) == [dai.CameraBoardSocket.CAM_A]


def test_resolve_candidate_sockets_falls_back_to_available_when_needed() -> None:
    requested = [dai.CameraBoardSocket.CAM_C]
    available = [dai.CameraBoardSocket.CAM_A, dai.CameraBoardSocket.CAM_B]
    assert webrtc._resolve_candidate_sockets(requested, available) == [
        dai.CameraBoardSocket.CAM_B,
        dai.CameraBoardSocket.CAM_A,
    ]


def test_build_ffmpeg_command_uses_passthrough_rtsp() -> None:
    command = webrtc.build_ffmpeg_command(rtsp_url="rtsp://localhost:8554/cam_a", fps=30)
    assert command[-1] == "rtsp://localhost:8554/cam_a"
    assert "-framerate" in command
    assert command[command.index("-framerate") + 1] == "30"
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-f") + 1] == "h264"


def test_h264_decoder_returns_rgb_arrays(monkeypatch) -> None:
    class FakeFrame:
        def to_ndarray(self, *, format: str):
            assert format == "rgb24"
            return np.zeros((2, 3, 3), dtype=np.uint8)

    class FakeCodec:
        def decode(self, payload: bytes):
            assert payload == b"packet"
            return [FakeFrame()]

    class FakeCodecContext:
        @staticmethod
        def create(codec: str, mode: str):
            assert codec == "h264"
            assert mode == "r"
            return FakeCodec()

    monkeypatch.setattr(webrtc.av, "CodecContext", FakeCodecContext)
    monkeypatch.setattr(webrtc.av, "Packet", lambda payload: payload)

    decoder = webrtc.H264Decoder()
    frames = decoder.decode(b"packet")

    assert len(frames) == 1
    assert frames[0].shape == (2, 3, 3)
