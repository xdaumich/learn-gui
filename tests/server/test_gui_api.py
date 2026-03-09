"""Tests for telemetry_console.gui_api."""

import json
import time

from fastapi.testclient import TestClient

from telemetry_console.gui_api import app


def test_gui_api_routes_exist():
    routes = {route.path for route in app.routes}
    assert "/health" in routes
    assert "/rerun/status" in routes
    assert "/robot/status" in routes
    assert "/cameras" in routes
    assert "/stream/{camera}" in routes
    assert "/recording/status" in routes
    assert "/recording/start" in routes
    assert "/recording/stop" in routes


def test_gui_api_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_robot_status_missing_heartbeat(monkeypatch, tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    monkeypatch.setenv("ROBOT_HEARTBEAT_PATH", str(heartbeat_path))

    client = TestClient(app)
    response = client.get("/robot/status")
    payload = response.json()

    assert response.status_code == 200
    assert payload["alive"] is False
    assert payload["age_s"] is None
    assert payload["step_count"] == 0


def test_robot_status_uses_fresh_heartbeat(monkeypatch, tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    heartbeat_path.write_text(
        json.dumps(
            {
                "alive": True,
                "updated_at_s": time.time(),
                "step_count": 42,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ROBOT_HEARTBEAT_PATH", str(heartbeat_path))
    monkeypatch.setenv("ROBOT_HEARTBEAT_MAX_AGE_S", "30")

    client = TestClient(app)
    response = client.get("/robot/status")
    payload = response.json()

    assert response.status_code == 200
    assert payload["alive"] is True
    assert isinstance(payload["age_s"], (int, float))
    assert payload["step_count"] == 42
