"""
Comprehensive pytest tests for Phoenix API incidents endpoints.

Tests without Docker/Database (uses mongomock + mocks).
- `client` fixture: no-op background pipeline (fast, state controlled)
- `client_with_pipeline`: real orchestrator with mocked LLM/Sandbox
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import status


class TestPostIncidents:
    """POST /api/incidents endpoint tests."""

    def test_valid_ci_payload_returns_202_incident_created(self, client, ci_payload):
        """Valid CI payload → 202 Accepted, incident_id INC-001, pipeline starts."""
        response = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["incident_id"] == "INC-001"
        assert data["status"] == "detected"
        assert "Pipeline started" in data["message"]

    def test_valid_docker_payload_returns_202(self, client, docker_payload):
        """Valid Docker payload → 202 Accepted, incident_id INC-001."""
        response = client.post(
            "/api/incidents",
            json=docker_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["incident_id"] == "INC-001"
        assert data["status"] == "detected"

    def test_missing_token_returns_401(self, client, ci_payload):
        """Missing X-Phoenix-Token header → 401 Unauthorized."""
        response = client.post("/api/incidents", json=ci_payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid or missing" in response.json()["detail"]

    def test_wrong_token_returns_401(self, client, ci_payload):
        """Wrong X-Phoenix-Token header → 401 Unauthorized."""
        response = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "wrong-secret"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_duplicate_incident_same_repo_commit_run_id(self, client, ci_payload):
        """Same (repo, commit, run_id) twice → returns same incident_id, status=duplicate."""
        # First request
        r1 = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )
        assert r1.status_code == status.HTTP_202_ACCEPTED
        incident_id_1 = r1.json()["incident_id"]
        assert incident_id_1 == "INC-001"

        # Second request — identical payload
        r2 = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )
        assert r2.status_code == status.HTTP_202_ACCEPTED
        data2 = r2.json()
        assert data2["incident_id"] == incident_id_1
        assert data2["status"] == "duplicate"

    def test_loop_guard_ignores_phoenix_fix_branch(self, client, ci_payload):
        """Branch phoenix/fix/INC-001 → status=ignored, empty incident_id."""
        payload = {**ci_payload, "branch": "phoenix/fix/INC-001"}

        response = client.post(
            "/api/incidents",
            json=payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "ignored"
        assert "Loop guard" in data["message"]

    def test_incident_counter_increments(self, client, ci_payload):
        """INC counter increments sequentially: INC-001, INC-002."""
        # First incident
        r1 = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )
        assert r1.json()["incident_id"] == "INC-001"

        # Second incident with a different commit (not a duplicate)
        payload2 = {**ci_payload, "commit": "def9876543210abc9876543210abc98765432109"}
        r2 = client.post(
            "/api/incidents",
            json=payload2,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )
        assert r2.json()["incident_id"] == "INC-002"

    def test_missing_required_fields_returns_422(self, client, ci_payload):
        """Missing repository → 422 Unprocessable Entity."""
        payload = {k: v for k, v in ci_payload.items() if k != "repository"}

        response = client.post(
            "/api/incidents",
            json=payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Missing required fields" in response.json()["detail"]

    def test_invalid_source_returns_422(self, client, ci_payload):
        """Invalid source value → 422 Unprocessable Entity."""
        payload = {**ci_payload, "source": "invalid_source"}

        response = client.post(
            "/api/incidents",
            json=payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Invalid source" in response.json()["detail"]


class TestGetIncidents:
    """GET /api/incidents endpoint tests."""

    def test_get_incidents_returns_list(self, client, ci_payload):
        """GET /api/incidents returns paginated list."""
        client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        response = client.get("/api/incidents")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "incidents" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert len(data["incidents"]) > 0

    def test_get_incidents_pagination(self, client, ci_payload):
        """GET /api/incidents?skip=0&limit=1 returns 1 item, total=3."""
        for i in range(3):
            payload = {**ci_payload, "commit": f"commit{i:040x}"}
            client.post(
                "/api/incidents",
                json=payload,
                headers={"X-Phoenix-Token": "test-secret-123"},
            )

        response = client.get("/api/incidents?skip=0&limit=1")
        data = response.json()
        assert len(data["incidents"]) == 1
        assert data["total"] == 3
        assert data["page_size"] == 1

    def test_get_incidents_filter_by_status(self, client, ci_payload):
        """GET /api/incidents?status=detected returns matching incidents."""
        client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        response = client.get("/api/incidents?status=detected")
        data = response.json()
        assert data["total"] >= 1
        assert all(inc["status"] == "detected" for inc in data["incidents"])


class TestGetIncidentDetail:
    """GET /api/incidents/{incident_id} endpoint tests."""

    def test_get_incident_detail_returns_full_document(self, client, ci_payload):
        """GET /api/incidents/{id} returns full incident with timeline."""
        create_resp = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )
        incident_id = create_resp.json()["incident_id"]

        response = client.get(f"/api/incidents/{incident_id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["incident_id"] == incident_id
        assert data["source"] == "github_ci"
        assert data["repository"] == "owner/repo"
        assert "timeline" in data
        assert len(data["timeline"]) > 0

    def test_get_nonexistent_incident_returns_404(self, client):
        """GET /api/incidents/INVALID → 404."""
        response = client.get("/api/incidents/INVALID")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestHealthEndpoint:
    """GET /health endpoint tests."""

    def test_health_check_returns_healthy(self, client):
        """GET /health returns {"status": "healthy"}."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "healthy"


class TestClassification:
    """Failure classification tests (integrated with endpoint)."""

    def test_code_level_error_proceeds_to_pipeline(self, client, ci_payload):
        """Code-level error (KeyError in logs) → 202 detected, pipeline queued."""
        response = client.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json()["status"] == "detected"

    def test_non_code_classification_via_mock(self, client, ci_payload):
        """Classifier returning non_code → endpoint still returns 202 detected
        (classification runs in background; endpoint only stores the incident)."""
        payload = {**ci_payload, "logs": "Connection timeout: failed to connect to redis"}

        with patch("app.orchestrator.FailureClassifier.classify") as mock_classify:
            mock_classify.return_value = ("non_code", "Network error")

            response = client.post(
                "/api/incidents",
                json=payload,
                headers={"X-Phoenix-Token": "test-secret-123"},
            )

        assert response.status_code == status.HTTP_202_ACCEPTED


class TestPipelineFlow:
    """End-to-end pipeline flow tests (mocked LLM + Sandbox, real orchestrator)."""

    def test_ci_payload_through_full_pipeline(
        self, client_with_pipeline, ci_payload
    ):
        """CI payload → incident created → pipeline runs → incident retrievable."""
        response = client_with_pipeline.post(
            "/api/incidents",
            json=ci_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        incident_id = response.json()["incident_id"]

        detail = client_with_pipeline.get(f"/api/incidents/{incident_id}")
        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["source"] == "github_ci"

    def test_docker_payload_through_pipeline(
        self, client_with_pipeline, docker_payload
    ):
        """Docker payload → incident created → source preserved."""
        response = client_with_pipeline.post(
            "/api/incidents",
            json=docker_payload,
            headers={"X-Phoenix-Token": "test-secret-123"},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        incident_id = response.json()["incident_id"]

        detail = client_with_pipeline.get(f"/api/incidents/{incident_id}")
        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["source"] == "docker_runtime"


class TestConcurrency:
    """Sequential ID and isolation tests."""

    def test_multiple_incidents_get_unique_sequential_ids(self, client, ci_payload):
        """Five distinct incidents get INC-001 … INC-005 in order."""
        ids = []
        for i in range(5):
            payload = {**ci_payload, "commit": f"{i:040x}"}
            r = client.post(
                "/api/incidents",
                json=payload,
                headers={"X-Phoenix-Token": "test-secret-123"},
            )
            assert r.status_code == status.HTTP_202_ACCEPTED
            ids.append(r.json()["incident_id"])

        assert ids == ["INC-001", "INC-002", "INC-003", "INC-004", "INC-005"]
        assert len(set(ids)) == 5
