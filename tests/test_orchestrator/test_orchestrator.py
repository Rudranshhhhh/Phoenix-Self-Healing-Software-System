"""Offline tests for the orchestrator: evidence building and the event flow (all fakes, no Docker/LLM)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.orchestrator import Orchestrator
from agent.orchestrator.evidence import build_evidence, split_error

APP = (
    'PRODUCTS = {"apple": {"cost": 10}}\n\n\n'
    "def get_product(name):\n"
    "    product = PRODUCTS[name]\n"
    '    return product["price"]\n'
)

TRACE = (
    "Traceback (most recent call last):\n"
    '  File "/app/app.py", line 12, in <module>\n'
    '    get_product("apple")\n'
    '  File "/app/app.py", line 6, in get_product\n'
    '    return product["price"]\n'
    '  File "/usr/local/lib/python3.12/collections/__init__.py", line 5, in __getitem__\n'
    "    raise KeyError(key)\n"
    "KeyError: 'price'\n"
)


def make_report(trace=TRACE):
    return SimpleNamespace(
        container_id="c1",
        container_name="phoenix-run-broken-app",
        error="KeyError: 'price'",
        stack_trace=trace,
        exit_code=1,
    )


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "broken_app"
    folder.mkdir()
    (folder / "app.py").write_text(APP, encoding="utf-8")
    return folder


# --- evidence -----------------------------------------------------------------


def test_split_error():
    assert split_error("KeyError: 'price'") == ("KeyError", "'price'")
    assert split_error("ZeroDivisionError") == ("ZeroDivisionError", "ZeroDivisionError")
    assert split_error("") == ("Error", "Unknown error")


def test_build_evidence_maps_container_paths(project):
    ev = build_evidence(make_report(), project)
    assert (ev["error_type"], ev["error_message"]) == ("KeyError", "'price'")
    assert (ev["file"], ev["line"], ev["function_name"]) == ("app.py", 6, "get_product")
    assert ev["relevant_code"].startswith("# FILE: app.py\n")
    assert 'return product["price"]' in ev["relevant_code"]
    assert "collections" not in ev["relevant_code"]


def test_build_evidence_without_source(tmp_path):
    ev = build_evidence(make_report(), tmp_path)
    assert (ev["file"], ev["line"]) == ("unknown", 0)
    assert ev["relevant_code"] is None


def test_build_evidence_ignores_paths_outside_project(project):
    trace = '  File "/app/../etc/passwd", line 1, in x\n' + TRACE
    ev = build_evidence(make_report(trace), project)
    assert "passwd" not in (ev["relevant_code"] or "")


# --- flow -----------------------------------------------------------------------


class FakeIngest:
    def __init__(self, up=True):
        self.up = up
        self.events = []

    def send(self, incident_id, event, **fields):
        self.events.append((event, fields))
        return {"id": "INC-101"} if self.up else None


class FakeEngine:
    def __init__(self, result):
        self.result = result
        self.evidence = None

    def run(self, evidence):
        self.evidence = evidence
        return self.result


class FakePipeline:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def run(self, **kwargs):
        kwargs["github_token_seen"] = os.environ.get("GITHUB_TOKEN")
        self.calls.append(kwargs)
        return self.outcome


def llm_result(success=True, empty=False):
    patches = (
        []
        if empty
        else [SimpleNamespace(file="app.py", old_code='product["price"]', new_code='product.get("price", 0)')]
    )
    return SimpleNamespace(
        success=success,
        error=None if success else "rate limited",
        patch=SimpleNamespace(explanation="Default the price", is_empty=empty, patches=patches),
        diagnosis=SimpleNamespace(
            root_cause="No price key",
            explanation="Uses cost",
            affected_file="app.py",
            affected_line=6,
            confidence=0.8,
        ),
    )


def sandbox_outcome(validated=True, pr=False):
    return SimpleNamespace(
        validation=SimpleNamespace(
            validated=validated,
            reason="All validation checks passed." if validated else "Patch rejected — tests failed",
            test_stdout="=== 1 passed in 0.1s ===" if validated else "=== 1 failed in 0.1s ===",
            test_stderr="",
            duration_seconds=1.5,
            completed_at=None,
            original_failure_resolved=validated,
        ),
        git=SimpleNamespace(success=False, branch_name="phoenix/fix/INC-101"),
        pull_request=SimpleNamespace(
            success=True, pr_number=3, pr_url="https://example.test/pull/3", head_branch="phoenix/fix/INC-101"
        )
        if pr
        else None,
        error=None,
    )


def make(project, tmp_path, llm=None, outcome=None, report="default", up=True):
    ingest = FakeIngest(up)
    engine = FakeEngine(llm or llm_result())
    pipeline = FakePipeline(outcome or sandbox_outcome())
    orch = Orchestrator(
        ingest=ingest,
        monitor=lambda _dir, _timeout: make_report() if report == "default" else report,
        engine_factory=lambda: engine,
        pipeline_factory=lambda _lint: pipeline,
        workspaces_root=tmp_path / "workspaces",
    )
    return orch, ingest, engine, pipeline


def names(ingest):
    return [event for event, _ in ingest.events]


def test_success_flow(project, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    orch, ingest, engine, pipeline = make(project, tmp_path)
    result = orch.run(project)

    assert result.status == "validated"
    assert result.dashboard_id == "INC-101"
    assert names(ingest) == ["detected", "diagnosing", "fix_proposed", "validating", "validated"]
    assert engine.evidence["file"] == "app.py"
    call = pipeline.calls[0]
    assert call["incident_id"] == "INC-101"
    assert (Path(call["repo_path"]) / ".git").is_dir()
    assert call["github_token_seen"] is None
    assert os.environ["GITHUB_TOKEN"] == "secret"


def test_pr_flow(project, tmp_path):
    orch, ingest, _, _ = make(project, tmp_path, outcome=sandbox_outcome(pr=True))
    assert orch.run(project).status == "pr_opened"
    assert names(ingest)[-1] == "pr_opened"


def test_rejected_flow(project, tmp_path):
    orch, ingest, _, _ = make(project, tmp_path, outcome=sandbox_outcome(validated=False))
    assert orch.run(project).status == "rejected"
    assert names(ingest)[-1] == "rejected"


def test_llm_error_reports_failed(project, tmp_path):
    orch, ingest, _, pipeline = make(project, tmp_path, llm=llm_result(success=False))
    result = orch.run(project)
    assert result.status == "failed"
    assert names(ingest) == ["detected", "diagnosing", "failed"]
    assert "rate limited" in ingest.events[-1][1]["message"]
    assert pipeline.calls == []


def test_empty_patch_reports_failed(project, tmp_path):
    orch, ingest, _, _ = make(project, tmp_path, llm=llm_result(empty=True))
    assert orch.run(project).status == "failed"
    assert names(ingest)[-1] == "failed"


def test_no_failure(project, tmp_path):
    orch, ingest, _, _ = make(project, tmp_path, report=None)
    assert orch.run(project).status == "no_failure"
    assert ingest.events == []


def test_dashboard_down_still_runs(project, tmp_path):
    orch, _, _, pipeline = make(project, tmp_path, up=False)
    result = orch.run(project)
    assert result.status == "validated"
    assert result.dashboard_id.startswith("local-")
    assert pipeline.calls[0]["incident_id"] == result.dashboard_id
