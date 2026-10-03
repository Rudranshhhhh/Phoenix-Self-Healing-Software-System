"""
Unit and integration tests for Phoenix Sample App.

Executed during CI validation and inside the Docker sandbox to verify fixes.
"""
import sys
from pathlib import Path
import pytest

# Ensure sample-app is importable
_app_dir = str(Path(__file__).resolve().parent.parent)
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import app as sample_app


@pytest.fixture(autouse=True)
def reset_health_state():
    """Ensure health status is reset to healthy before and after each test."""
    sample_app._is_healthy = True
    yield
    sample_app._is_healthy = True


@pytest.fixture
def client():
    """Flask test client fixture."""
    sample_app.app.config["TESTING"] = True
    with sample_app.app.test_client() as client:
        yield client


def test_health_endpoint_healthy(client):
    """GET /health should return 200 and healthy status by default."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "sample-backend"


def test_break_and_restore_health(client):
    """GET /break-health should make /health return 500 until /restore-health."""
    # Break health
    break_res = client.get("/break-health")
    assert break_res.status_code == 200

    # Verify unhealthy
    unhealthy_res = client.get("/health")
    assert unhealthy_res.status_code == 500
    assert unhealthy_res.get_json()["status"] == "unhealthy"

    # Restore health
    restore_res = client.get("/restore-health")
    assert restore_res.status_code == 200

    # Verify healthy again
    healthy_res = client.get("/health")
    assert healthy_res.status_code == 200
    assert healthy_res.get_json()["status"] == "healthy"


def test_leak_endpoint(client):
    """GET /leak should allocate strings and return 200."""
    initial_len = len(sample_app._memory_leak_bucket)
    response = client.get("/leak")
    assert response.status_code == 200
    assert len(sample_app._memory_leak_bucket) == initial_len + 15


def test_cpu_endpoint(client):
    """GET /cpu should trigger background burner and return 200."""
    response = client.get("/cpu")
    assert response.status_code == 200
    assert "launched" in response.get_json()["message"]
