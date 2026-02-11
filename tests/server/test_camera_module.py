# tests/server/test_camera_module.py
"""Tests for telemetry_console.camera (no recording dependency)."""

import inspect


def test_camera_module_does_not_import_data_log():
    """The camera module must not depend on recording."""
    import telemetry_console.camera as cam
    source = inspect.getsource(cam)
    assert "data_log" not in source
    assert "RecordingManager" not in source


def test_ensure_streaming_signature_has_no_recording_manager():
    import telemetry_console.camera as cam
    sig = inspect.signature(cam.ensure_streaming)
    assert "recording_manager" not in sig.parameters


def test_camera_relay_publisher_has_no_recording_manager():
    import telemetry_console.camera as cam
    sig = inspect.signature(cam.CameraRelayPublisher.__init__)
    assert "recording_manager" not in sig.parameters


def test_camera_constants():
    from telemetry_console.camera import DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS
    assert DEFAULT_WIDTH == 640
    assert DEFAULT_HEIGHT == 480
    assert DEFAULT_FPS == 30
