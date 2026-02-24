import depthai as dai

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
