from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_recording_start_stop_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_LOG_DIR", str(tmp_path))
    app.state.recording_manager = None

    client = TestClient(app)

    start_resp = client.post("/recording/start")
    assert start_resp.status_code == 200
    start_payload = start_resp.json()
    assert start_payload["active"] is True
    run_id = start_payload["run_id"]

    status_payload = client.get("/recording/status").json()
    assert status_payload["active"] is True
    assert status_payload["run_id"] == run_id

    stop_payload = client.post("/recording/stop").json()
    assert stop_payload["active"] is False
    assert stop_payload["run_id"] == run_id

    final_status = client.get("/recording/status").json()
    assert final_status["active"] is False
    assert final_status["run_id"] == run_id
