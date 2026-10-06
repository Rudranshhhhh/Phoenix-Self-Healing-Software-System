"""Tests for POST /api/ingest/events and the ingest helpers."""

from __future__ import annotations

import json
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


# --- Diff line numbers --------------------------------------------------------


def hunk_headers(diff):
    return [line for line in diff.splitlines() if line.startswith("@@")]


def test_build_diff_explicit_start_line():
    patch = InFilePatch(file="app/pricing.py", old_code=OLD_CODE, new_code=NEW_CODE, start_line=16)
    diff = build_diff([patch])
    assert hunk_headers(diff) == ["@@ -16,2 +16,2 @@"]
    # Only the header moves; the body is what difflib produced.
    unshifted = build_diff([InFilePatch(file="app/pricing.py", old_code=OLD_CODE, new_code=NEW_CODE)])
    assert diff.replace("@@ -16,2 +16,2 @@", "@@ -1,2 +1,2 @@") == unshifted


def test_build_diff_explicit_start_line_beats_diagnosis():
    patch = InFilePatch(file="app/pricing.py", old_code=OLD_CODE, new_code=NEW_CODE, start_line=40)
    assert hunk_headers(build_diff([patch], "app/pricing.py", 17)) == ["@@ -40,2 +40,2 @@"]


def test_build_diff_start_line_from_diagnosis():
    patch = InFilePatch(file="app/pricing.py", old_code=OLD_CODE, new_code=NEW_CODE)
    # Line 17 is the second line of old_code (the first one that changes), so old_code starts at 16.
    assert hunk_headers(build_diff([patch], "app/pricing.py", 17)) == ["@@ -16,2 +16,2 @@"]
    assert hunk_headers(build_diff([patch], "/app/app/pricing.py", 17)) == ["@@ -16,2 +16,2 @@"]


def test_build_diff_diagnosis_fallback_limits():
    patch = InFilePatch(file="app/pricing.py", old_code=OLD_CODE, new_code=NEW_CODE)
    other = InFilePatch(file="app/orders.py", old_code="a\n", new_code="b\n")
    assert hunk_headers(build_diff([patch], "app/pricing.py", 1)) == ["@@ -1,2 +1,2 @@"]  # would be line 0
    assert hunk_headers(build_diff([patch], "app/orders.py", 17)) == ["@@ -1,2 +1,2 @@"]  # other file
    assert hunk_headers(build_diff([patch], None, None)) == ["@@ -1,2 +1,2 @@"]
    # More than one patch: no guessing.
    assert hunk_headers(build_diff([patch, other], "app/pricing.py", 17)) == ["@@ -1,2 +1,2 @@", "@@ -1 +1 @@"]


def test_build_diff_multiple_patches_with_start_lines():
    diff = build_diff(
        [
            InFilePatch(file="app/pricing.py", old_code=OLD_CODE, new_code=NEW_CODE, start_line=16),
            InFilePatch(file="app/orders.py", old_code="a\n", new_code="b\n", start_line=9),
        ]
    )
    assert hunk_headers(diff) == ["@@ -16,2 +16,2 @@", "@@ -9 +9 @@"]


def test_fix_proposed_diff_uses_diagnosis_line(client):
    inc = run_success(client, "d1")
    assert hunk_headers(inc["patch"]["diff"]) == ["@@ -16,2 +16,2 @@"]


def test_fix_proposed_diff_uses_start_line(client):
    inc = post(
        client,
        "d2",
        "fix_proposed",
        patch={
            "explanation": "x",
            "patches": [{"file": "app/pricing.py", "old_code": OLD_CODE, "new_code": NEW_CODE, "start_line": 30}],
        },
    )
    assert hunk_headers(inc["patch"]["diff"]) == ["@@ -30,2 +30,2 @@"]


def test_bad_start_line(client):
    body = {
        "incident_id": "d3",
        "event": "fix_proposed",
        "patch": {"patches": [{"file": "a.py", "old_code": "a", "new_code": "b", "start_line": 0}]},
    }
    assert client.post(URL, json=body).status_code == 422


# --- Validation environment and fix branch -------------------------------------


def test_environment_and_fix_branch_round_trip(client):
    agent_id = str(uuid.uuid4())
    inc = run_success(client, agent_id)
    assert inc["validation"]["environment"] is None  # run_success never sends one
    assert inc["fix_branch"] == f"phoenix/fix/{agent_id}"  # from pr_opened head_branch

    post(client, "e1", "detected")
    assert post(client, "e1", "validating", environment="local")["validation"] is None
    inc = post(
        client,
        "e1",
        "validated",
        branch="phoenix/fix/INC-102",
        validation={"validated": True, "test_stdout": "=== 3 passed ===", "environment": "docker"},
    )
    assert inc["validation"]["environment"] == "docker"
    assert inc["fix_branch"] == "phoenix/fix/INC-102"
    assert client.get("/api/incidents/INC-102").json() == inc


def test_environment_from_validating_is_kept(client):
    post(client, "e2", "validating", environment="docker")
    inc = post(client, "e2", "rejected", validation={"validated": False, "reason": "tests failed"})
    assert inc["validation"]["environment"] == "docker"
    assert inc["fix_branch"] is None

    post(client, "e3", "validating", environment="local")
    assert post(client, "e3", "failed", message="sandbox crashed")["validation"]["environment"] == "local"


def test_bad_environment(client):
    body = {"incident_id": "e4", "event": "validating", "environment": "kubernetes"}
    assert client.post(URL, json=body).status_code == 422


def test_old_store_entries_without_new_fields(client, store):
    inc = post(client, "e5", "validated", validation={"validated": True})
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    del raw["incidents"][inc["id"]]["fix_branch"]
    del raw["incidents"][inc["id"]]["validation"]["environment"]
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    again = IncidentStore(store.path).get(inc["id"])
    assert again.fix_branch is None and again.validation.environment is None


def test_fixture_environment_and_fix_branch(client, monkeypatch):
    monkeypatch.setenv("DEMO_FIXTURES", "1")
    for incident_id in ("INC-005", "INC-006", "INC-007"):
        assert client.get(f"/api/incidents/{incident_id}").json()["validation"]["environment"] == "docker"
    assert client.get("/api/incidents/INC-007").json()["fix_branch"] == "phoenix/fix/INC-007"
    assert client.get("/api/incidents/INC-005").json()["fix_branch"] is None
    assert client.get("/api/incidents/INC-001").json()["fix_branch"] is None


# --- List size ----------------------------------------------------------------


def test_default_page_size_is_100(client):
    for _ in range(25):
        post(client, str(uuid.uuid4()), "detected")
    listed = client.get("/api/incidents").json()
    assert listed["page_size"] == 100
    assert listed["total"] == 25
    assert len(listed["items"]) == 25
    assert client.get("/api/incidents?page_size=100").status_code == 200
    assert client.get("/api/incidents?page_size=101").status_code == 422
