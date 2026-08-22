"""
Phoenix Agent — Restart Database Strategy

Restarts the PostgreSQL container via Docker SDK.
Waits for postgres to become connectable before declaring success.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import docker
import docker.errors
import psycopg2

from agent.events.incident import FailureType, Incident, RecoveryResult
from agent.recovery.strategies.base import RecoveryStrategy

logger = logging.getLogger(__name__)


class RestartDatabaseStrategy(RecoveryStrategy):
    """Recovery strategy: restart the PostgreSQL container."""

    name = "RestartDatabaseStrategy"
    priority = 15

    def __init__(
        self,
        docker_socket: str,
        postgres_container_name: str,
        postgres_dsn: str,
        wait_timeout_seconds: int = 60,
    ) -> None:
        self._socket = docker_socket
        self._pg_container = postgres_container_name
        self._dsn = postgres_dsn
        self._timeout = wait_timeout_seconds
        self._client: Optional[docker.DockerClient] = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._socket)
        return self._client

    def can_handle(self, incident: Incident) -> bool:
        return incident.failure_type == FailureType.DATABASE_UNREACHABLE

    def execute(self, incident: Incident) -> RecoveryResult:
        logger.info("RestartDatabaseStrategy: restarting postgres container '%s'", self._pg_container)
        try:
            client = self._get_client()
            container = client.containers.get(self._pg_container)
            container.restart(timeout=10)

            # Wait for PostgreSQL to accept connections
            deadline = time.monotonic() + self._timeout
            while time.monotonic() < deadline:
                try:
                    conn = psycopg2.connect(self._dsn + " connect_timeout=3")
                    conn.close()
                    logger.info("RestartDatabaseStrategy: PostgreSQL is accepting connections")
                    return RecoveryResult(
                        success=True,
                        strategy_name=self.name,
                        message="PostgreSQL restarted and is accepting connections.",
                        attempt=incident.retry_count + 1,
                    )
                except psycopg2.OperationalError:
                    time.sleep(3)

            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"PostgreSQL did not become connectable within {self._timeout}s.",
                attempt=incident.retry_count + 1,
                error="timeout",
            )
        except Exception as exc:
            logger.exception("RestartDatabaseStrategy: error: %s", exc)
            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"Database restart failed: {exc}",
                attempt=incident.retry_count + 1,
                error=str(exc),
            )
