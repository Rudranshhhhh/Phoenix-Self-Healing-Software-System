"""Tests for POST /api/demo/run (the simulated INC-109 replay)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import demo_run, ingest, main
from app.ingest import IncidentStore

URL = "/api/demo/run"


@pytest.fixture
def store(tmp_path, monkeypatch):
    fresh = IncidentStore(tmp_path / "incidents.json")
    monkeypatch.setattr(ingest, "store", fresh)
    monkeypatch.setattr(main, "store", fresh)
    monkeypatch.setenv("DEMO_FIXTURES", "0")
    # Short but non-zero, so a second POST lands while the run is still going.
    monkeypatch.setattr(demo_run, "DELAYS", [(0.1, "diagnosing"), (0.2, "fix_proposed"), (0.3, "validating"), (0.4, "validated")])
    return fresh


@pytest.fixture
def client(store):
    # The context manager keeps one event loop alive across requests, so the background replay keeps running.
    with TestClient(main.app) as c:
        yield c


def wait_until_finished(timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while demo_run.running_id() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert demo_run.running_id() is None, "simulated run did not finish"


def test_post_returns_202_and_incident_id(client):
    response = client.post(URL)
    assert response.status_code == 202
    incident_id = response.json()["incident_id"]
    assert incident_id.startswith("INC-")

    detail = client.get(f"/api/incidents/{incident_id}").json()
    assert detail["status"] == "detected"
    assert detail["simulated"] is True
    assert detail["timeline"][0]["message"].startswith("Simulated run: ")
    wait_until_finished()


def test_second_post_while_running_returns_409_with_same_id(client):
    first = client.post(URL).json()["incident_id"]
    second = client.post(URL)
    assert second.status_code == 409
    assert second.json() == {"incident_id": first}
    wait_until_finished()


def test_sequence_ends_validated(client):
    incident_id = client.post(URL).json()["incident_id"]
    wait_until_finished()

    detail = client.get(f"/api/incidents/{incident_id}").json()
    assert detail["status"] == "validated"
    assert detail["simulated"] is True
    assert [t["status"] for t in detail["timeline"]] == [
        "detected", "diagnosing", "fix_proposed", "validating", "validated",
    ]
    assert detail["source"] == {
        "type": "docker_runtime", "workflow_run_url": None, "container": "phoenix-run-broken_app", "commit_sha": None,
    }
    assert detail["validation"]["result"] == "PASS"
    assert detail["validation"]["environment"] == "local"
    assert detail["validation"]["tests_run"] == 1
    assert detail["validation"]["tests_passed"] == 1
    assert detail["fix_branch"] == f"phoenix/fix/{incident_id}"
    assert detail["patch"]["diff"].split("\n")[2].startswith("@@ -9")
    assert [f["line"] for f in detail["error"]["frames"] if f["blame"]] == [9]

    summary = client.get("/api/incidents").json()["items"]
    assert [(i["id"], i["simulated"]) for i in summary] == [(incident_id, True)]


def test_new_run_removes_previous_simulated_incident(client, store):
    ingest.store.apply(ingest.IngestEvent(incident_id="real-run", event="detected"))
    first = client.post(URL).json()["incident_id"]
    wait_until_finished()

    second = client.post(URL).json()["incident_id"]
    assert second != first
    assert client.get(f"/api/incidents/{first}").status_code == 404
    ids = {i.id for i in store.list()}
    assert second in ids and first not in ids
    assert len(ids) == 2  # the real incident is kept
    wait_until_finished()


def test_failure_marks_run_rejected_and_clears_flag(client, monkeypatch):
    real_payload = demo_run._payload

    def broken(agent_id, event, incident_id):
        if event == "validating":
            raise RuntimeError("boom")
        return real_payload(agent_id, event, incident_id)

    monkeypatch.setattr(demo_run, "_payload", broken)
    incident_id = client.post(URL).json()["incident_id"]
    wait_until_finished()
    assert client.get(f"/api/incidents/{incident_id}").json()["status"] == "rejected"
