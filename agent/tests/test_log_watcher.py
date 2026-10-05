"""Unit tests for the live log watcher. Use fakes: no Docker engine needed."""
from __future__ import annotations

import threading

from agent.runtime.docker_runtime import DockerRuntime
from agent.runtime.log_watcher import (
    TracebackDetector,
    detect_failures,
    iter_lines,
    watch_for_failure,
)

APP_LOG = (
    "INFO:root:web-app listening on 8080\n"
    "ERROR:root:request failed: /product\n"
    "Traceback (most recent call last):\n"
    '  File "/app/app.py", line 25, in do_GET\n'
    '    self._reply(200, str(get_product("apple")))\n'
    '  File "/app/app.py", line 12, in get_product\n'
    '    return product["price"]\n'
    "KeyError: 'price'\n"
    'INFO:root:127.0.0.1 "GET /product HTTP/1.1" 500 -\n'
)


class FakeContainer:
    def __init__(self, chunks, status="running", exit_code=None, block=None):
        self.id = "abc123def456"
        self.name = "phoenix-web-demo"
        self.status = status
        self.attrs = {"State": {"ExitCode": exit_code, "OOMKilled": False}}
        self._chunks = chunks
        self._block = block

    def reload(self):
        pass

    def logs(self, **kwargs):
        if kwargs.get("stream"):
            return self._stream()
        return b"".join(self._chunks)

    def _stream(self):
        yield from self._chunks
        if self._block is not None:
            self._block.wait(timeout=5)


def _runtime():
    return DockerRuntime(client=object())


def test_iter_lines_handles_split_chunks_and_trailing_partial_line():
    chunks = [b"hello wo", b"rld\nsecond\nthi", b"rd"]
    assert list(iter_lines(chunks)) == ["hello world", "second", "third"]


def test_detector_extracts_error_and_trace_ignoring_log_noise():
    detector = TracebackDetector()
    results = [r for r in (detector.feed(line) for line in APP_LOG.splitlines()) if r]
    assert len(results) == 1
    error, trace = results[0]
    assert error == "KeyError: 'price'"
    assert trace.startswith("Traceback (most recent call last):")
    assert "get_product" in trace and "listening" not in trace


def test_detector_ignores_normal_logs_and_abandons_broken_block():
    detector = TracebackDetector()
    assert detector.feed("INFO: all good") is None
    assert detector.feed("Traceback (most recent call last):") is None
    assert detector.feed('  File "a.py", line 1, in f') is None
    assert detector.feed("") is None
    assert detector.feed("KeyError: 'x'") is None


def test_detect_failures_works_across_arbitrary_chunk_boundaries():
    data = APP_LOG.encode()
    chunks = [data[i:i + 7] for i in range(0, len(data), 7)]
    assert [e for e, _ in detect_failures(chunks)] == ["KeyError: 'price'"]


def test_detect_failures_reports_every_traceback():
    data = (APP_LOG + APP_LOG.replace("KeyError: 'price'", "ValueError: x")).encode()
    assert [e for e, _ in detect_failures([data])] == ["KeyError: 'price'", "ValueError: x"]


def test_watch_reports_traceback_from_running_container():
    container = FakeContainer([APP_LOG.encode()])
    report = watch_for_failure(_runtime(), container, timeout=5)
    assert report.error == "KeyError: 'price'"
    assert report.status == "running" and report.exit_code is None
    assert report.container_id == "abc123def456"
    assert set(report.to_dict()) >= {"error", "stack_trace", "container_id"}


def test_watch_returns_none_on_timeout_when_nothing_fails():
    release = threading.Event()
    container = FakeContainer([b"INFO: all good\n"], block=release)
    try:
        assert watch_for_failure(_runtime(), container, timeout=0.2) is None
    finally:
        release.set()


def test_watch_falls_back_to_exit_code_when_stream_ends_without_traceback():
    container = FakeContainer([b"killed\n"], status="exited", exit_code=137)
    report = watch_for_failure(_runtime(), container, timeout=5)
    assert report.exit_code == 137 and "137" in report.error


def test_watch_returns_none_when_stream_ends_and_container_exited_cleanly():
    container = FakeContainer([b"bye\n"], status="exited", exit_code=0)
    assert watch_for_failure(_runtime(), container, timeout=5) is None


def test_watch_fills_exit_code_when_container_already_stopped():
    container = FakeContainer([APP_LOG.encode()], status="exited", exit_code=1)
    report = watch_for_failure(_runtime(), container, timeout=5)
    assert report.error == "KeyError: 'price'" and report.exit_code == 1