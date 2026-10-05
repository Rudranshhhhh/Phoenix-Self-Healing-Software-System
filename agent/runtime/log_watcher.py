"""
Phoenix Agent - Live Log Watcher

Watches a RUNNING container's log stream and reports the first Python
traceback as soon as it appears, without waiting for the container to exit.
Pure helpers (iter_lines, TracebackDetector, detect_failures) are separated
from the Docker-facing watch_for_failure() so they are easy to test.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Iterable, Iterator, Optional

from agent.runtime.docker_runtime import DockerRuntime, FailureReport

logger = logging.getLogger(__name__)

_TRACEBACK_HEADER = "Traceback (most recent call last):"
_STOPPED_STATES = ("exited", "dead")


def iter_lines(chunks: Iterable[bytes]) -> Iterator[str]:
    """Turn arbitrary byte chunks from a log stream into complete text lines."""
    buffer = b""
    for chunk in chunks:
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            yield raw.decode("utf-8", errors="replace").rstrip("\r")
    if buffer:
        yield buffer.decode("utf-8", errors="replace").rstrip("\r")


class TracebackDetector:
    """
    Line-by-line traceback detector.

    feed() returns (error_line, stack_trace) on the line that completes a
    traceback, otherwise None. A blank line inside a traceback abandons it.
    """

    def __init__(self) -> None:
        self._block: list[str] = []

    def feed(self, line: str) -> Optional[tuple[str, str]]:
        if line.strip().endswith(_TRACEBACK_HEADER):
            self._block = [line[line.index("Traceback"):]]
            return None
        if not self._block:
            return None
        if not line.strip():
            self._block = []
            return None
        self._block.append(line)
        if line[0].isspace():
            return None
        error = line.strip()
        stack_trace = "\n".join(self._block)
        self._block = []
        return error, stack_trace


def detect_failures(chunks: Iterable[bytes]) -> Iterator[tuple[str, str]]:
    """Yield (error_line, stack_trace) for every traceback found in a log stream."""
    detector = TracebackDetector()
    for line in iter_lines(chunks):
        result = detector.feed(line)
        if result is not None:
            yield result


def watch_for_failure(
    runtime: DockerRuntime,
    container: Any,
    timeout: float = 60.0,
    tail: Any = "all",
) -> Optional[FailureReport]:
    """
    Follow the container's logs and return a FailureReport for the first
    traceback seen, or None if nothing happens within `timeout` seconds.

    tail="all" also scans existing logs; tail=0 looks only at new output.
    If the stream ends first (container stopped), falls back to
    runtime.collect_failure() so crashes without a traceback are still reported.
    """
    events: queue.Queue = queue.Queue()

    def _reader() -> None:
        stream = None
        try:
            stream = container.logs(stream=True, follow=True, stdout=True, stderr=True, tail=tail)
            for failure in detect_failures(stream):
                events.put(failure)
                return
        except Exception:
            logger.exception("LogWatcher: log stream failed")
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            events.put(None)

    threading.Thread(target=_reader, daemon=True, name="phoenix-log-watcher").start()

    try:
        item = events.get(timeout=timeout)
    except queue.Empty:
        return None
    if item is None:
        return runtime.collect_failure(container)

    error, stack_trace = item
    container.reload()
    stopped = container.status in _STOPPED_STATES
    state = container.attrs.get("State", {}) if stopped else {}
    return FailureReport(
        container_id=container.id,
        container_name=container.name,
        error=error,
        stack_trace=stack_trace,
        exit_code=state.get("ExitCode"),
        status=container.status,
        oom_killed=bool(state.get("OOMKilled")),
        logs_tail=container.logs(tail=200).decode("utf-8", errors="replace"),
    )