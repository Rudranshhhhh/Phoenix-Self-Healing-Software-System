"""Tests for POST /api/ingest/events and the ingest helpers."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app import ingest, main
from app.ingest import InFilePatch, IncidentStore, build_diff, count_tests, parse_frames

URL = "/api/ingest/events"

TRACE = (
    "Traceback (most recent call last):\n"
    '  File "/app/app/routes/orders.py", line 58, in create_order\n'
    "    order = checkout(payload)\n"
    '  File "/app/app/pricing.py", line 17, in cart_total\n'
    '    return sum(item["price"] * item["qty"] for item in items)\n'
    "KeyError: 'price'\n"
)

OLD_CODE = 'def cart_total(items):\n    return sum(item["price"] for item in items)\n'
NEW_CODE = 'def cart_total(items):\n    return sum(item.get("price", 0) for item in items)\n'


@pytest.fixture
def store(tmp_path, monkeypatch):
    fresh = IncidentStore(tmp_path / "incidents.json")
    monkeypatch.setattr(ingest, "store", fresh)
    monkeypatch.setattr(main, "store", fresh)
    monkeypatch.setenv("DEMO_FIXTURES", "0")
    monkeypatch.delenv("PHOENIX_INGEST_TOKEN", raising=False)
    return fresh


@pytest.fixture
def client(store):
    return TestClient(main.app)


def post(client, incident_id, event, **extra):
    response = client.post(URL, json={"incident_id": incident_id, "event": event, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def run_success(client, incident_id):
    post(
        client,
        incident_id,
        "detected",
        source={"type": "docker_runtime", "container": "orders-api"},
        error={"exception_type": "KeyError", "message": "'price'", "stack_trace": TRACE},
    )
    post(client, incident_id, "diagnosing")
    post(
        client,
        incident_id,
        "fix_proposed",
        diagnosis={
            "root_cause": "Old carts store unit_price",
            "explanation": "cart_total indexes item['price'] directly.",
            "affected_file": "app/pricing.py",
            "affected_line": 17,
            "confidence": 0.82,
        },
        patch={
            "explanation": "Fall back when an item has no price.",
            "patches": [{"file": "app/pricing.py", "old_code": OLD_CODE, "new_code": NEW_CODE}],
        },
    )
    post(client, incident_id, "validating")
    post(
        client,
        incident_id,
        "validated",
        validation={
            "validated": True,
            "test_stdout": "collected 18 items\n=== 18 passed in 4.2s ===",
            "duration_seconds": 31.5,
            "original_failure_resolved": True,
        },
    )
    return post(
        client,
        incident_id,
        "pr_opened",
        pull_request={
            "pr_number": None,
            "pr_url": "https://github.com/phoenix-demo/orders-api/pull/12",
            "head_branch": f"phoenix/fix/{incident_id}",
        },
    )


# --- Endpoint -----------------------------------------------------------------


def test_full_success_sequence(client):
    agent_id = str(uuid.uuid4())
    inc = run_success(client, agent_id)

    assert inc["id"] == "INC-101"
    assert inc["status"] == "pr_opened"
    assert [t["status"] for t in inc["timeline"]] == [
        "detected", "diagnosing", "fix_proposed", "validating", "validated", "pr_opened",
    ]
    assert inc["source"]["container"] == "orders-api"

    frames = inc["error"]["frames"]
    assert [f["blame"] for f in frames] == [False, True]
    assert frames[1]["code"].startswith("return sum(")

    assert inc["patch"]["diff"].startswith("--- a/app/pricing.py\n+++ b/app/pricing.py\n")
    assert inc["patch"]["files_changed"] == ["app/pricing.py"]

    v = inc["validation"]
    assert (v["result"], v["tests_run"], v["tests_passed"]) == ("PASS", 18, 18)
    assert v["bug_reproduced_before_patch"] is None
    assert v["bug_reproduces_after_patch"] is False

    assert inc["pull_request"] == {
        "number": None,
        "url": "https://github.com/phoenix-demo/orders-api/pull/12",
        "branch": f"phoenix/fix/{agent_id}",
        "state": "open",
    }

    listed = client.get("/api/incidents").json()
    assert listed["total"] == 1
    assert listed["items"][0]["pr_url"].endswith("/pull/12")
    assert client.get("/api/incidents/INC-101").json() == inc


def test_rejected_validation(client):
    post(client, "a", "detected", error={"exception_type": "KeyError", "message": "'price'", "stack_trace": TRACE})
    inc = post(
        client,
        "a",
        "rejected",
        validation={
            "validated": False,
            "reason": "Patch rejected — tests failed",
            "test_stdout": "=== 2 failed, 16 passed in 4.0s ===",
        },
    )
    v = inc["validation"]
    assert inc["status"] == "rejected"
    assert (v["result"], v["tests_run"], v["tests_passed"]) == ("FAIL", 18, 16)
    assert v["rejection_reason"] == "Patch rejected — tests failed"


def test_failed_maps_to_rejected(client):
    inc = post(client, "b", "failed", message="LLM returned no patch")
    assert inc["status"] == "rejected"
    assert inc["validation"]["result"] == "FAIL"
    assert inc["validation"]["rejection_reason"] == "LLM returned no patch"
    assert inc["timeline"][-1]["status"] == "rejected"


def test_repeated_status_replaces_timeline_entry(client):
    post(client, "c", "diagnosing", message="one")
    inc = post(client, "c", "diagnosing", message="two")
    assert [(t["status"], t["message"]) for t in inc["timeline"]] == [("diagnosing", "two")]


def test_dashboard_ids(client):
    first = str(uuid.uuid4())
    assert post(client, first, "detected")["id"] == "INC-101"
    assert post(client, first, "diagnosing")["id"] == "INC-101"
    assert post(client, "INC-555", "detected")["id"] == "INC-555"
    assert post(client, str(uuid.uuid4()), "detected")["id"] == "INC-556"


def test_token(client, monkeypatch):
    monkeypatch.setenv("PHOENIX_INGEST_TOKEN", "t1")
    body = {"incident_id": "x", "event": "detected"}
    assert client.post(URL, json=body).status_code == 401
    assert client.post(URL, json=body, headers={"X-Phoenix-Token": "wrong"}).status_code == 401
    assert client.post(URL, json=body, headers={"X-Phoenix-Token": "t1"}).status_code == 200


def test_bad_body(client):
    assert client.post(URL, json={"incident_id": "x", "event": "exploded"}).status_code == 422
    assert client.post(URL, json={"event": "detected"}).status_code == 422


def test_restart_keeps_incidents(client, store):
    run_success(client, "p")
    again = IncidentStore(store.path)
    assert [i.id for i in again.list()] == ["INC-101"]
    assert again.get("INC-101").status == "pr_opened"


def test_demo_fixtures_flag(client, monkeypatch):
    assert client.get("/api/incidents/INC-001").status_code == 404

    monkeypatch.setenv("DEMO_FIXTURES", "1")
    post(client, "INC-007", "detected")
    ids = [i["id"] for i in client.get("/api/incidents?page_size=100").json()["items"]]
    assert "INC-001" in ids
    assert ids.count("INC-007") == 1
    assert client.get("/api/incidents/INC-007").json()["status"] == "detected"


# --- Helpers ------------------------------------------------------------------


def test_count_tests():
    assert count_tests("=== 2 failed, 16 passed, 1 error in 3s ===") == (19, 16)
    assert count_tests("no summary here") == (None, None)


def test_build_diff_keeps_dot_paths():
    diff = build_diff([InFilePatch(file="./.github/workflows/ci.yml", old_code="a\n", new_code="b")])
    assert diff.splitlines()[:2] == ["--- a/.github/workflows/ci.yml", "+++ b/.github/workflows/ci.yml"]
    assert diff.endswith("+b\n")


def test_parse_frames_blame():
    assert [f["blame"] for f in parse_frames(TRACE, None, None)] == [False, True]
    assert [f["blame"] for f in parse_frames(TRACE, "app/routes/orders.py", 58)] == [True, False]
    assert parse_frames("", None, None) == []
