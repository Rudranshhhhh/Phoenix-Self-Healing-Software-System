"""
Phoenix Agent — Docker Logs Collector Plugin

Reads the last N lines of a container's stdout/stderr logs
and pattern-matches for known error signatures.

Design: Returns log_errors list — detected errors become input
to the DetectionEngine and DiagnosisEngine for log-based incidents.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import docker
import docker.errors
from docker.models.containers import Container

from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)

# Known error patterns to scan for in logs
ERROR_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)(error|exception|traceback|fatal|panic|segfault|oom|killed)"),
    re.compile(r"(?i)(connection refused|cannot connect|no route to host)"),
    re.compile(r"(?i)(out of memory|memory limit exceeded)"),
    re.compile(r"(?i)(disk full|no space left)"),
]


class LogsCollector:
    """
    Collector plugin that reads Docker container logs and extracts error lines.

    Tail length is configurable via settings.
    Multiple error patterns are matched against each log line.
    """

    name: str
    service: str

    def __init__(
        self,
        service: str,
        container_name: str,
        docker_socket: str,
        tail_lines: int = 50,
    ) -> None:
        self.service = service
        self.container_name = container_name
        self.name = f"logs:{service}"
        self._docker_socket = docker_socket
        self._tail_lines = tail_lines
        self._client = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._docker_socket)
        return self._client

    def collect(self) -> ServiceSnapshot:
        """Read container logs and extract error lines. Never raises."""
        log_errors: list[str] = []

        try:
            client = self._get_client()
            container: Container = client.containers.get(self.container_name)
            raw_logs = container.logs(
                tail=self._tail_lines,
                stdout=True,
                stderr=True,
                timestamps=False,
            )
            log_text = raw_logs.decode("utf-8", errors="replace")
            lines = log_text.splitlines()
            for line in lines:
                if any(pattern.search(line) for pattern in ERROR_PATTERNS):
                    log_errors.append(line.strip()[:500])  # cap line length

            if log_errors:
                logger.debug("LogsCollector[%s]: found %d error lines", self.service, len(log_errors))

        except docker.errors.NotFound:
            logger.warning("LogsCollector[%s]: container '%s' not found", self.service, self.container_name)
        except docker.errors.APIError as exc:
            logger.error("LogsCollector[%s]: Docker API error: %s", self.service, exc)
        except Exception as exc:
            logger.exception("LogsCollector[%s]: unexpected error: %s", self.service, exc)

        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status="unknown",
            log_errors=log_errors,
            collected_at=datetime.now(timezone.utc),
        )

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        return len(snapshot.log_errors) == 0
