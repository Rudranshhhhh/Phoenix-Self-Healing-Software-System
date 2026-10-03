"""
Backend test — reproduces the severity-filter count bug.

Bug location:
    backend/services/incident_service.py  -> list_incidents()
    backend/repositories/incident_repository.py -> count_incidents()

Bug:
    list_incidents() passes `severity` to the item query
    (repo.list_incidents) but NOT to the count query
    (repo.count_incidents). As a result, when the API is filtered by
    severity, the returned `items` are correct but the `total` (and the
    derived `pages`) ignore the severity filter and count ALL incidents.

This is a unit test. The MongoDB collection accessor is replaced with an
in-memory fake so NO real database connection is required. It exercises the
REAL production functions in incident_repository.py and incident_service.py,
so the failure is caused purely by the production bug — not by missing
dependencies, fixtures, or database setup.

Run:
    python -m pytest backend/tests/test_incident_severity_count.py -v
"""
from __future__ import annotations

import backend.repositories.incident_repository as incident_repository
import backend.services.incident_service as incident_service


# ============================================================================ #
# In-memory fake MongoDB collection                                              #
# ============================================================================ #
# Mimics only the slice of pymongo's Collection API that incident_repository
# actually uses: find() (with .sort/.skip/.limit chaining) and count_documents().

def _matches(doc: dict, query: dict) -> bool:
    """Return True if doc satisfies every key/value in the query dict."""
    for key, value in query.items():
        if doc.get(key) != value:
            return False
    return True


class _FakeCursor:
    """Minimal chainable cursor over an in-memory list of docs."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = list(docs)

    def sort(self, field: str, direction: int) -> "_FakeCursor":
        # pymongo: DESCENDING == -1, ASCENDING == 1
        self._docs.sort(key=lambda d: d.get(field, ""), reverse=(direction < 0))
        return self

    def skip(self, n: int) -> "_FakeCursor":
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int) -> "_FakeCursor":
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeCollection:
    """In-memory stand-in for mongo.incidents()."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = {d["incident_id"]: dict(d) for d in docs}

    def find(self, query: dict) -> _FakeCursor:
        matched = [d for d in self._docs.values() if _matches(d, query)]
        return _FakeCursor(matched)

    def count_documents(self, query: dict) -> int:
        return sum(1 for d in self._docs.values() if _matches(d, query))


# ============================================================================ #
# Test data: 2 LOW incidents + 1 HIGH incident                                   #
# ============================================================================ #

_INCIDENTS: list[dict] = [
    {
        "incident_id": "inc-low-1",
        "service": "sample-backend",
        "status": "RESOLVED",
        "severity": "LOW",
        "resolved": True,
        "detected_at": "2026-10-01T10:00:00+00:00",
    },
    {
        "incident_id": "inc-low-2",
        "service": "sample-backend",
        "status": "RESOLVED",
        "severity": "LOW",
        "resolved": True,
        "detected_at": "2026-10-01T11:00:00+00:00",
    },
    {
        "incident_id": "inc-high-1",
        "service": "sample-backend",
        "status": "DIAGNOSING",
        "severity": "HIGH",
        "resolved": False,
        "detected_at": "2026-10-02T09:00:00+00:00",
    },
]


# ============================================================================ #
# Tests                                                                         #
# ============================================================================ #

def test_no_filter_returns_all_incidents(monkeypatch):
    """
    Sanity check: with no filters, list_incidents() returns all 3 incidents
    and reports total = 3. This proves the in-memory fake and test data are
    set up correctly, so any later failure must be caused by the production
    bug — not by the test harness.
    """
    fake_collection = _FakeCollection(_INCIDENTS)
    monkeypatch.setattr(incident_repository.mongo, "incidents", lambda: fake_collection)

    result = incident_service.list_incidents(page=1, page_size=20)

    assert len(result["items"]) == 3, f"expected 3 items, got {len(result['items'])}"
    assert result["total"] == 3, f"expected total = 3, got {result['total']}"


def test_severity_filter_applies_to_total_count(monkeypatch):
    """
    BUG REPRODUCTION.

    Filtering incidents by severity="HIGH" must narrow BOTH the returned
    `items` AND the `total` count used for pagination.

    The `items` query in repo.list_incidents() correctly applies the severity
    filter, so items contains only the 1 HIGH incident.

    But incident_service.list_incidents() does NOT pass `severity` to
    repo.count_incidents(), so `total` counts ALL incidents (3) instead of
    only the HIGH ones (1). This assertion therefore FAILS — which is the
    bug we want Phoenix to diagnose.

    Expected: total = 1   (only the HIGH incident)
    Actual:   total = 3   (severity ignored by the count query)
    """
    fake_collection = _FakeCollection(_INCIDENTS)
    monkeypatch.setattr(incident_repository.mongo, "incidents", lambda: fake_collection)

    result = incident_service.list_incidents(severity="HIGH", page=1, page_size=20)

    # 1. Items ARE correctly filtered to only HIGH — this passes.
    assert len(result["items"]) == 1, (
        f"items should contain only the HIGH incident, got {len(result['items'])}"
    )
    assert result["items"][0]["severity"] == "HIGH"
    assert result["items"][0]["incident_id"] == "inc-high-1"

    # 2. total must reflect the SAME severity filter — this FAILS due to the bug.
    assert result["total"] == 1, (
        f"expected total = 1 (only HIGH incidents), actual total = {result['total']}"
    )
