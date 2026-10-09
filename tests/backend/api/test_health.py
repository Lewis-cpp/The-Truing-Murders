import pytest
from fastapi.testclient import TestClient

from backend.main import app

pytestmark = pytest.mark.api


@pytest.mark.integration
def test_ready_checks_real_database(monkeypatch, database_url):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_database_failure_preserves_liveness_and_hides_connection_details(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://unused:private-test-password@127.0.0.1:1/unavailable"
    )
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        ready = client.get("/api/v1/ready")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable", "database": "unavailable"}
    assert "private-test-password" not in ready.text
    assert ready.headers["cache-control"] == "no-store"
