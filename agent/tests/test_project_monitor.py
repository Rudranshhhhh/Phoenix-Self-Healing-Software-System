"""Unit tests for the project monitor. Use fakes: no Docker engine needed."""
from __future__ import annotations

import json

import pytest
from docker.errors import BuildError

from agent.runtime import project_monitor
from agent.runtime.docker_runtime import FailureReport
from agent.runtime.project_monitor import ProjectError, main, monitor_project, to_agent_event


def _report():
    return FailureReport(
        container_id="abc123", container_name="phoenix-run-app", error="KeyError: 'price'",
        stack_trace="Traceback...", exit_code=None, status="running", oom_killed=False, logs_tail="...",
    )


class FakeRuntime:
    def __init__(self, build_error=None):
        self.calls = []
        self._build_error = build_error

    def build_image(self, path, tag):
        self.calls.append(("build", tag))
        if self._build_error:
            raise self._build_error
        return "sha256:abc"

    def start(self, tag, name):
        self.calls.append(("start", name))
        return object()

    def remove(self, name):
        self.calls.append(("remove", name))


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "My App!"
    folder.mkdir()
    (folder / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return folder


def test_to_agent_event_has_exactly_the_team_contract_keys():
    assert to_agent_event(_report()) == {
        "error": "KeyError: 'price'", "stack_trace": "Traceback...", "container_id": "abc123",
    }


def test_missing_folder_and_missing_dockerfile_raise_project_error(tmp_path):
    runtime = FakeRuntime()
    with pytest.raises(ProjectError, match="not found"):
        monitor_project(tmp_path / "nope", runtime=runtime)
    (tmp_path / "empty").mkdir()
    with pytest.raises(ProjectError, match="No Dockerfile"):
        monitor_project(tmp_path / "empty", runtime=runtime)
    assert runtime.calls == []


def test_monitor_builds_starts_watches_and_cleans_up_with_safe_name(project, monkeypatch):
    seen = {}

    def fake_watch(runtime, container, timeout, tail):
        seen.update(timeout=timeout, tail=tail)
        return _report()

    monkeypatch.setattr(project_monitor, "watch_for_failure", fake_watch)
    runtime = FakeRuntime()
    result = monitor_project(project, runtime=runtime, timeout=7)
    assert result.error == "KeyError: 'price'"
    assert seen == {"timeout": 7, "tail": "all"}
    assert runtime.calls == [
        ("build", "phoenix-run-my-app:latest"),
        ("start", "phoenix-run-my-app"),
        ("remove", "phoenix-run-my-app"),
    ]


def test_container_is_removed_even_if_watching_crashes(project, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("watcher exploded")

    monkeypatch.setattr(project_monitor, "watch_for_failure", boom)
    runtime = FakeRuntime()
    with pytest.raises(RuntimeError):
        monitor_project(project, runtime=runtime)
    assert runtime.calls[-1][0] == "remove"


def test_build_failure_becomes_project_error_and_no_container_started(project):
    runtime = FakeRuntime(build_error=BuildError("pip failed", iter([])))
    with pytest.raises(ProjectError, match="build failed"):
        monitor_project(project, runtime=runtime)
    assert [c[0] for c in runtime.calls] == ["build"]


def test_cli_prints_team_format_by_default_and_full_report_on_request(monkeypatch, capsys):
    monkeypatch.setattr(project_monitor, "monitor_project", lambda *a, **k: _report())
    assert main(["some/folder"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"error", "stack_trace", "container_id"}
    assert main(["some/folder", "--full"]) == 0
    assert "exit_code" in json.loads(capsys.readouterr().out)


def test_cli_reports_no_failure_and_project_errors(monkeypatch, capsys):
    monkeypatch.setattr(project_monitor, "monitor_project", lambda *a, **k: None)
    assert main(["x"]) == 0
    assert "No failure detected" in capsys.readouterr().out

    def fail(*a, **k):
        raise ProjectError("No Dockerfile found in: x")

    monkeypatch.setattr(project_monitor, "monitor_project", fail)
    assert main(["x"]) == 2
    assert "No Dockerfile" in capsys.readouterr().out