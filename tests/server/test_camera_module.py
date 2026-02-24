# tests/server/test_camera_module.py
"""Tests for telemetry_console.camera constants and public API."""


def test_camera_constants():
    from telemetry_console.camera import DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS
    assert DEFAULT_WIDTH == 640
    assert DEFAULT_HEIGHT == 480
    assert DEFAULT_FPS == 30


def test_build_h264_pipeline_importable():
    from telemetry_console.camera import build_h264_pipeline
    assert callable(build_h264_pipeline)
