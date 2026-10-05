"""Unit tests for saving failures to disk."""
from __future__ import annotations

import json

from agent.runtime import project_monitor
from agent.runtime.docker_runtime import FailureReport
from agent.runtime.failure_store import list_failures, load_failure, save_failure
from agent.runtime.project_monitor import main, to_agent_event


def _report(name="phoenix-run-app", error="KeyError: 'price'"):
    return FailureReport(
        container_id="abc123", container_name=name, error=error, stack_trace="Traceback...",
        exit_code=1, status="exited", oom_killed=False, logs_tail="log line",
    )


def test_save_creates_missing_folders_and_a_readable_json_file(tmp_path):
    path = save_failure(_report(), tmp_path / "a" / "b")
    assert path.is_file() and path.suffix == ".json"
    data = load_failure(path)
    assert set(data) == {"saved_at", "event", "details"}
    assert data["details"]["exit_code"] == 1 and data["details"]["logs_tail"] == "log line"


def test_saved_event_matches_the_team_contract_exactly(tmp_path):
    report = _report()
    data = load_failure(save_failure(report, tmp_path))
    assert data["event"] == to_agent_event(report)
    assert set(data["event"]) == {"error", "stack_trace", "container_id"}


def test_unsafe_container_names_become_safe_file_names(tmp_path):
    path = save_failure(_report(name='we/ird:"name"?'), tmp_path)
    assert path.parent == tmp_path
    assert not any(c in path.name for c in '/:"?')


def test_two_quick_saves_never_overwrite_each_other(tmp_path):
    paths = {save_failure(_report(), tmp_path) for _ in range(5)}
    assert len(paths) == 5 and len(list(tmp_path.glob("*.json"))) == 5


def test_no_temp_files_are_left_behind(tmp_path):
    save_failure(_report(), tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_list_failures_is_oldest_first_and_ignores_other_files(tmp_path):
    first = save_failure(_report(error="first"), tmp_path)
    second = save_failure(_report(error="second"), tmp_path)
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert list_failures(tmp_path) == [first, second]
    assert list_failures(tmp_path / "missing") == []


def test_cli_saves_only_when_asked_and_keeps_stdout_pure_json(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(project_monitor, "monitor_project", lambda *a, **k: _report())
    assert main(["folder"]) == 0
    capsys.readouterr()
    assert list(tmp_path.iterdir()) == []

    out_dir = tmp_path / "saved"
    assert main(["folder", "--save-dir", str(out_dir)]) == 0
    captured = capsys.readouterr()
    assert set(json.loads(captured.out)) == {"error", "stack_trace", "container_id"}
    assert "Saved failure report to" in captured.err
    assert len(list_failures(out_dir)) == 1