"""
Pytest configuration and fixtures for Phoenix API tests.

Uses mongomock for MongoDB, mocked LLMEngine/SandboxPipeline for external deps.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import mongomock
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path + env setup — must happen before any phoenix-api imports
# ---------------------------------------------------------------------------
phoenix_api_dir = Path(__file__).parent.parent.parent / "phoenix-api"
sys.path.insert(0, str(phoenix_api_dir))

os.environ["PHOENIX_WEBHOOK_SECRET"] = "test-secret-123"
os.environ["MONGO_URI"] = "mongomock://localhost"
os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["GITHUB_TOKEN"] = "test-github-token"
os.environ["GITHUB_REPO"] = "test/repo"
# Point to the workspace root so git commands at least find *a* repo
os.environ["PHOENIX_REPO_PATH"] = str(Path(__file__).parent.parent.parent)

# ---------------------------------------------------------------------------
# Pre-stub agent modules — before any phoenix-api module is imported
# ---------------------------------------------------------------------------
_agent_stub       = MagicMock()
_ai_stub          = MagicMock()
_llm_stub         = MagicMock()
_diagnosis_stub   = MagicMock()
_sandbox_stub     = MagicMock()
_sandbox_models_stub = MagicMock()

sys.modules["agent"]                        = _agent_stub
sys.modules["agent.ai"]                     = _ai_stub
sys.modules["agent.ai.llm_engine"]          = _llm_stub
sys.modules["agent.ai.llm_engine.diagnosis"] = _diagnosis_stub
sys.modules["agent.sandbox"]                = _sandbox_stub
sys.modules["agent.sandbox.models"]         = _sandbox_models_stub

# ---------------------------------------------------------------------------
# Single shared mongomock client — recreated once per session, reset per test
# ---------------------------------------------------------------------------
_MOCK_CLIENT = mongomock.MongoClient()
_MOCK_DB = _MOCK_CLIENT["phoenix"]


def _reset_db():
    """Drop and recreate collections so every test starts clean."""
    for name in list(_MOCK_DB.list_collection_names()):
        _MOCK_DB.drop_collection(name)

    _MOCK_DB.create_collection("counters")
    _MOCK_DB.counters.insert_one({"_id": "incident_seq", "seq": 0})

    _MOCK_DB.create_collection("incidents")
    _MOCK_DB.incidents.create_index("incident_id", unique=True)
    _MOCK_DB.incidents.create_index("source")
    _MOCK_DB.incidents.create_index("status")
    _MOCK_DB.incidents.create_index([("created_at", -1)])
    _MOCK_DB.incidents.create_index(
        [("repository", 1), ("commit", 1), ("run_id", 1)],
        sparse=True,
    )


# Patch get_database at module level — done once, always returns _MOCK_DB
import app.database as _db_mod          # noqa: E402  (import after sys.path set)
_db_mod._client = _MOCK_CLIENT          # make the module think it's initialised
_original_get_database = _db_mod.get_database


def _patched_get_database():
    return _MOCK_DB


_db_mod.get_database = _patched_get_database
_db_mod.init_database = lambda: True   # no-op


# ---------------------------------------------------------------------------
# Build the FastAPI app once (after patching get_database)
# ---------------------------------------------------------------------------
from app.main import app as _app        # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_db_between_tests():
    """Reset MongoDB state before every test."""
    _reset_db()
    yield


@pytest.fixture
def mock_llm_engine():
    """Provide a working LLMEngine mock via sys.modules."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.error = None
    mock_result.evidence = None
    mock_result.diagnosis = MagicMock()
    mock_result.diagnosis.root_cause = "Test root cause"

    mock_patch_obj = MagicMock()
    mock_patch_obj.is_empty = False
    mock_patch_obj.patches = [
        MagicMock(file="app.py", old_code="x = None", new_code="x = {}")
    ]
    mock_patch_obj.explanation = "Test patch explanation"
    mock_result.patch = mock_patch_obj

    mock_instance = MagicMock()
    mock_instance.run.return_value = mock_result

    mock_class = MagicMock(return_value=mock_instance)
    _llm_stub.LLMEngine = mock_class
    return _llm_stub


@pytest.fixture
def mock_sandbox_pipeline():
    """Provide a working SandboxPipeline mock via sys.modules."""
    mock_validation = MagicMock()
    mock_validation.validated = True
    mock_validation.build_passed = True
    mock_validation.lint_passed = True
    mock_validation.tests_passed = True
    mock_validation.original_failure_resolved = True
    mock_validation.reason = ""
    mock_validation.model_dump = MagicMock(return_value={"validated": True})

    mock_git = MagicMock()
    mock_git.success = True
    mock_git.branch_name = "phoenix/fix/INC-001"
    mock_git.commit_sha = "aaabbbcccddd1111222233334444555566667777"
    mock_git.commit_message = "fix(INC-001): test fix"
    mock_git.error = None

    mock_pr = MagicMock()
    mock_pr.success = True
    mock_pr.pr_number = 42
    mock_pr.pr_url = "https://github.com/test/repo/pull/42"
    mock_pr.title = "fix(INC-001): automated Phoenix fix"
    mock_pr.error = None

    mock_outcome = MagicMock()
    mock_outcome.incident_id = "INC-001"
    mock_outcome.validated = True
    mock_outcome.validation = mock_validation
    mock_outcome.git = mock_git
    mock_outcome.pull_request = mock_pr
    mock_outcome.pull_request_url = "https://github.com/test/repo/pull/42"
    mock_outcome.error = None
    mock_outcome.summary = MagicMock(return_value="VALIDATED ✓")

    mock_instance = MagicMock()
    mock_instance.run.return_value = mock_outcome

    mock_class = MagicMock(return_value=mock_instance)
    _sandbox_stub.SandboxPipeline = mock_class
    _sandbox_stub.SandboxConfig = MagicMock()
    _sandbox_models_stub.SandboxConfig = MagicMock()
    return _sandbox_stub


@pytest.fixture
def mock_orchestrator_process(monkeypatch):
    """
    Bypass the heavy process_incident() background task entirely.
    Tests that only need incident creation use this for speed and isolation.
    """
    from app.routers.incidents import orchestrator

    def _noop(incident_id: str):
        pass

    monkeypatch.setattr(orchestrator, "process_incident", _noop)


@pytest.fixture
def client(mock_llm_engine, mock_sandbox_pipeline, mock_orchestrator_process):
    """
    FastAPI TestClient.
    DB is reset by the autouse `reset_db_between_tests` fixture before this runs.
    Pipeline is a no-op so tests control their own state.
    """
    return TestClient(_app)


@pytest.fixture
def client_with_pipeline(mock_llm_engine, mock_sandbox_pipeline):
    """
    FastAPI TestClient where the real orchestrator pipeline runs (mocked LLM/Sandbox).
    Used by pipeline-flow tests.
    """
    return TestClient(_app)


# ---------------------------------------------------------------------------
# Payload fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ci_payload():
    """Sample GitHub Actions CI failure payload."""
    return {
        "source": "github_ci",
        "repository": "owner/repo",
        "commit": "abc1234567890def1234567890def12345678901",
        "branch": "main",
        "run_id": "12345",
        "run_url": "https://github.com/owner/repo/actions/runs/12345",
        "workflow": "tests",
        "job": "test",
        "stage": "test",
        "logs": (
            "test_app.py::test_get_user FAILED\n"
            "app.py:3: in get_user\n"
            "    return user['name']\n"
            "E   KeyError: 'name'\n"
            "================================ 1 failed in 0.42s ================================"
        ),
    }


@pytest.fixture
def docker_payload():
    """Sample Docker runtime incident payload."""
    return {
        "source": "docker_runtime",
        "repository": "owner/repo",
        "commit": "def1234567890abc1234567890abc12345678901",
        "branch": "main",
        "container_name": "app-1",
        "error_type": "TypeError",
        "error_message": "'NoneType' object is not subscriptable",
        "logs": "Traceback (most recent call last)...",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 42, in get_user\n"
            "    return user['name']\n"
            "TypeError: 'NoneType' object is not subscriptable"
        ),
    }
