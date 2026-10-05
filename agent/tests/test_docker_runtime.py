"""Unit tests for the Docker runtime. Use fakes: no Docker engine needed."""
from __future__ import annotations

import pytest
from docker.errors import NotFound

from agent.runtime.docker_runtime import DockerRuntime, extract_traceback

CRASH_LOGS = """broken-app starting
Traceback (most recent call last):
  File "/app/app.py", line 14, in <module>
    print(get_product("apple"), flush=True)
  File "/app/app.py", line 9, in get_product
    return product["price"]
           ~~~~~~~^^^^^^^^^^
KeyError: 'price'
"""


class FakeContainer:
    def __init__(self, status="exited", exit_code=1, oom=False, logs=CRASH_LOGS, stop_after=0):
        self.id = "abc123def456"
        self.name = "phoenix-demo-app"
        self.status = status
        self.attrs = {"State": {"ExitCode": exit_code, "OOMKilled": oom}}
        self._logs = logs
        self._stop_after = stop_after
        self._reloads = 0
        self.removed = False

    def reload(self):
        self._reloads += 1
        if self._stop_after and self._reloads >= self._stop_after:
            self.status = "exited"

    def logs(self, tail=200):
        return self._logs.encode("utf-8")

    def remove(self, force=False):
        self.removed = True


class FakeContainers:
    def __init__(self, existing=None):
        self.existing = existing
        self.run_kwargs = None

    def get(self, name):
        if self.existing is None:
            raise NotFound("no such container")
        return self.existing

    def run(self, image, **kwargs):
        self.run_kwargs = {"image": image, **kwargs}
        return FakeContainer(status="running")


class FakeClient:
    def __init__(self, existing=None):
        self.containers = FakeContainers(existing)


def test_extract_traceback_finds_error_and_full_trace():
    error, trace = extract_traceback(CRASH_LOGS)
    assert error == "KeyError: 'price'"
    assert trace.startswith("Traceback (most recent call last):")
    assert 'File "/app/app.py", line 9, in get_product' in trace
    assert "broken-app starting" not in trace


def test_extract_traceback_uses_last_traceback_and_ignores_log_prefix():
    logs = "[2026] ERROR in app: boom\n" + CRASH_LOGS + CRASH_LOGS.replace("KeyError: 'price'", "ValueError: x")
    assert extract_traceback(logs)[0] == "ValueError: x"


@pytest.mark.parametrize("logs", ["", "all fine", "Traceback (most recent call last):\n  File \"a.py\", line 1, in f"])
def test_extract_traceback_returns_empty_when_incomplete(logs):
    assert extract_traceback(logs) == ("", "")


def test_collect_failure_reports_crash():
    report = DockerRuntime(client=FakeClient()).collect_failure(FakeContainer())
    assert report.error == "KeyError: 'price'"
    assert report.container_id == "abc123def456"
    assert report.exit_code == 1 and report.status == "exited"
    assert "get_product" in report.stack_trace
    assert set(report.to_dict()) >= {"error", "stack_trace", "container_id"}


def test_collect_failure_none_for_clean_exit_and_running():
    runtime = DockerRuntime(client=FakeClient())
    assert runtime.collect_failure(FakeContainer(exit_code=0)) is None
    assert runtime.collect_failure(FakeContainer(status="running", exit_code=None)) is None


def test_collect_failure_without_traceback_falls_back_to_exit_code():
    report = DockerRuntime(client=FakeClient()).collect_failure(
        FakeContainer(exit_code=137, oom=True, logs="killed")
    )
    assert report.oom_killed is True
    assert "137" in report.error and "OOMKilled" in report.error
    assert report.stack_trace == ""


def test_wait_for_exit_detects_stop_and_times_out(monkeypatch):
    monkeypatch.setattr("agent.runtime.docker_runtime.time.sleep", lambda s: None)
    runtime = DockerRuntime(client=FakeClient())
    assert runtime.wait_for_exit(FakeContainer(status="running", stop_after=3), timeout=5) is True
    assert runtime.wait_for_exit(FakeContainer(status="running"), timeout=0.05, poll=0.01) is False


def test_start_labels_container_and_removes_old_one():
    old = FakeContainer()
    client = FakeClient(existing=old)
    DockerRuntime(client=client).start("img:latest", "phoenix-demo-app")
    assert old.removed is True
    assert client.containers.run_kwargs["detach"] is True
    assert client.containers.run_kwargs["labels"] == {"phoenix.managed": "true"}


def test_remove_is_silent_when_container_missing():
    DockerRuntime(client=FakeClient(existing=None)).remove("nope")