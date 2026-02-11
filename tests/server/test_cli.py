"""Tests for CLI entry points."""

import importlib

import pytest


def test_cli_module_imports():
    mod = importlib.import_module("telemetry_console.cli")
    assert callable(getattr(mod, "run_gui", None))
    assert callable(getattr(mod, "run_camera", None))
    assert callable(getattr(mod, "run_robot", None))
    assert callable(getattr(mod, "run_recorder", None))
    assert callable(getattr(mod, "run_replay", None))


def test_parse_grpc_host_port() -> None:
    mod = importlib.import_module("telemetry_console.cli")
    host, port = mod._parse_grpc_host_port("rerun+http://127.0.0.1:9876/proxy")
    assert host == "127.0.0.1"
    assert port == 9876


def test_wait_for_grpc_listener_success(monkeypatch) -> None:
    mod = importlib.import_module("telemetry_console.cli")

    class _DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(mod.socket, "create_connection", lambda *_a, **_k: _DummyConn())
    mod._wait_for_grpc_listener(
        grpc_url="rerun+http://127.0.0.1:9876/proxy",
        timeout_s=0.2,
        retry_interval_s=0.05,
    )


def test_wait_for_grpc_listener_timeout(monkeypatch) -> None:
    mod = importlib.import_module("telemetry_console.cli")

    def _raise(*_a, **_k):
        raise OSError("unreachable")

    monkeypatch.setattr(mod.socket, "create_connection", _raise)
    with pytest.raises(RuntimeError):
        mod._wait_for_grpc_listener(
            grpc_url="rerun+http://127.0.0.1:9876/proxy",
            timeout_s=0.2,
            retry_interval_s=0.05,
        )
