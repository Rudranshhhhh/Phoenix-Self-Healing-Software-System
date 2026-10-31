from datetime import datetime, timezone

from app.analysis_store import AnalysisStore
from app.database import get_database


def test_enqueue_creates_and_requeues_analysis():
    first = AnalysisStore.enqueue("alice/demo", "alice")
    assert first["status"] == "queued"
    assert AnalysisStore.get("alice/demo", "alice")["status"] == "queued"

    claimed = AnalysisStore.claim("worker-1", 300)
    assert claimed["repository"] == "alice/demo"
    assert claimed["status"] == "processing"

    result = {
        "repository": "alice/demo",
        "worker_id": "worker-1",
        "status": "ready",
        "health": {"healthy": True},
    }
    updated = AnalysisStore.report("alice/demo", "worker-1", result)
    assert updated["status"] == "ready"
    assert AnalysisStore.get("alice/demo", "alice")["result"] == result

    AnalysisStore.enqueue("alice/demo", "alice")
    assert AnalysisStore.get("alice/demo", "alice")["status"] == "queued"


def test_analysis_result_requires_current_worker_lease():
    AnalysisStore.enqueue("alice/demo", "alice")
    assert AnalysisStore.report(
        "alice/demo",
        "wrong-worker",
        {"repository": "alice/demo", "worker_id": "wrong-worker", "status": "ready"},
    ) is None
