"""
Phoenix Agent - Docker Runtime

Builds an image, runs it as a container, watches it, and turns a crash into
a FailureReport ({error, stack_trace, container_id, ...}) for the next stage.
Uses the Python Docker SDK; Docker Desktop (the engine) must be running.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import docker
from docker.errors import NotFound

logger = logging.getLogger(__name__)

PHOENIX_LABEL = "phoenix.managed"
_TRACEBACK_HEADER = "Traceback (most recent call last):"
_STOPPED_STATES = ("exited", "dead")


@dataclass
class FailureReport:
    """What the Docker runtime hands to the rest of Phoenix."""
    container_id: str
    container_name: str
    error: str
    stack_trace: str
    exit_code: Optional[int]
    status: str
    oom_killed: bool
    logs_tail: str

    def to_dict(self) -> dict:
        return asdict(self)


def extract_traceback(logs: str) -> tuple[str, str]:
    """
    Return (error_line, stack_trace) for the LAST Python traceback in `logs`.
    Returns ("", "") when there is no complete traceback.
    """
    lines = logs.splitlines()
    start = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().endswith(_TRACEBACK_HEADER):
            start = i
            break
    if start is None:
        return "", ""

    block = [lines[start][lines[start].index("Traceback"):]]
    for line in lines[start + 1:]:
        if not line.strip():
            break
        block.append(line)
        if not line[0].isspace():      # first unindented line = "KeyError: 'price'"
            return line.strip(), "\n".join(block)
    return "", ""


class DockerRuntime:
    """Thin, testable wrapper around the Docker SDK."""

    def __init__(self, client: Any = None) -> None:
        self._client = client if client is not None else docker.from_env()

    def build_image(self, context_dir: Path, tag: str) -> str:
        """Build an image from a folder containing a Dockerfile."""
        image, _ = self._client.images.build(path=str(context_dir), tag=tag, rm=True)
        return image.id

    def remove(self, name: str) -> None:
        """Force-remove a container by name. Silent if it does not exist."""
        try:
            self._client.containers.get(name).remove(force=True)
        except NotFound:
            pass

    def start(self, image_tag: str, name: str) -> Any:
        """Start a labelled container (replacing any old one with the same name)."""
        self.remove(name)
        return self._client.containers.run(
            image_tag, name=name, detach=True, labels={PHOENIX_LABEL: "true"}
        )

    def wait_for_exit(self, container: Any, timeout: float = 60.0, poll: float = 1.0) -> bool:
        """Poll until the container stops. False if it is still running at timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            container.reload()
            if container.status in _STOPPED_STATES:
                return True
            time.sleep(poll)
        return False

    def collect_failure(self, container: Any, tail: int = 200) -> Optional[FailureReport]:
        """Build a FailureReport if the container crashed, else None."""
        container.reload()
        if container.status not in _STOPPED_STATES:
            return None
        state = container.attrs.get("State", {})
        exit_code = state.get("ExitCode")
        oom = bool(state.get("OOMKilled"))
        if exit_code == 0 and not oom:
            return None

        logs = container.logs(tail=tail).decode("utf-8", errors="replace")
        error, stack_trace = extract_traceback(logs)
        if not error:
            error = f"container exited with code {exit_code}" + (" (OOMKilled)" if oom else "")
        return FailureReport(
            container_id=container.id,
            container_name=container.name,
            error=error,
            stack_trace=stack_trace,
            exit_code=exit_code,
            status=container.status,
            oom_killed=oom,
            logs_tail=logs,
        )