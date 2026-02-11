"""Server smoke tests."""

from fastapi.testclient import TestClient

from main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rerun_status_endpoint_shape() -> None:
    client = TestClient(app)
    response = client.get("/rerun/status")

    payload = response.json()
    assert response.status_code == 200
    assert "running" in payload
    assert "web_url" in payload
