"""
Phoenix Agent — Restart Container Strategy

Restarts a stopped/crashed container via Docker SDK.
Waits for the container to reach 'running' state with timeout.
Uses exponential backoff on Docker API errors.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import docker
import docker.errors

from agent.events.incident import FailureType, Incident, RecoveryResult
from agent.recovery.strategies.base import RecoveryStrategy

logger = logging.getLogger(__name__)

_HANDLED_TYPES = {
    FailureType.CONTAINER_DOWN,
    FailureType.REPEATED_RESTARTS,
    FailureType.HIGH_MEMORY,  # restart to reclaim memory
}


class RestartContainerStrategy(RecoveryStrategy):
    """
    Recovery strategy: restart the affected container via Docker SDK.

    Applicable to: CONTAINER_DOWN, REPEATED_RESTARTS, HIGH_MEMORY.
    Waits up to `wait_timeout_seconds` for container to become running.
    """

    name = "RestartContainerStrategy"
    priority = 10  # high priority

    def __init__(
        self,
        docker_socket: str,
        wait_timeout_seconds: int = 60,
    ) -> None:
        self._socket = docker_socket
        self._timeout = wait_timeout_seconds
        self._client: Optional[docker.DockerClient] = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._socket)
        return self._client

    def can_handle(self, incident: Incident) -> bool:
        return incident.failure_type in _HANDLED_TYPES

    def execute(self, incident: Incident) -> RecoveryResult:
        container_name = incident.container_name
        logger.info(
            "RestartContainerStrategy: restarting '%s' (attempt %d)",
            container_name, incident.retry_count + 1,
        )
        try:
            client = self._get_client()
            container = client.containers.get(container_name)
            container.restart(timeout=10)

            # Wait for running state
            deadline = time.monotonic() + self._timeout
            while time.monotonic() < deadline:
                container.reload()
                if container.status == "running":
                    logger.info(
                        "RestartContainerStrategy: '%s' is running", container_name
                    )
                    return RecoveryResult(
                        success=True,
                        strategy_name=self.name,
                        message=f"Container '{container_name}' restarted successfully.",
                        attempt=incident.retry_count + 1,
                    )
                time.sleep(2)

            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"Container '{container_name}' did not reach 'running' within {self._timeout}s.",
                attempt=incident.retry_count + 1,
                error="timeout",
            )

        except docker.errors.NotFound:
            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"Container '{container_name}' not found.",
                attempt=incident.retry_count + 1,
                error="not_found",
            )
        except Exception as exc:
            logger.exception("RestartContainerStrategy: unexpected error: %s", exc)
            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"Restart failed: {exc}",
                attempt=incident.retry_count + 1,
                error=str(exc),
            )
