"""
Phoenix Agent — Restart Redis Strategy

Restarts the Redis container via Docker SDK.
Verifies Redis accepts PING before declaring success.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import docker
import docker.errors
import redis as redis_lib
import redis.exceptions

from agent.events.incident import FailureType, Incident, RecoveryResult
from agent.recovery.strategies.base import RecoveryStrategy

logger = logging.getLogger(__name__)


class RestartRedisStrategy(RecoveryStrategy):
    """Recovery strategy: restart the Redis container."""

    name = "RestartRedisStrategy"
    priority = 15

    def __init__(
        self,
        docker_socket: str,
        redis_container_name: str,
        redis_host: str,
        redis_port: int,
        wait_timeout_seconds: int = 45,
    ) -> None:
        self._socket = docker_socket
        self._redis_container = redis_container_name
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._timeout = wait_timeout_seconds
        self._client: Optional[docker.DockerClient] = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._socket)
        return self._client

    def can_handle(self, incident: Incident) -> bool:
        return incident.failure_type == FailureType.REDIS_DOWN

    def execute(self, incident: Incident) -> RecoveryResult:
        logger.info("RestartRedisStrategy: restarting redis container '%s'", self._redis_container)
        try:
            client = self._get_client()
            container = client.containers.get(self._redis_container)
            container.restart(timeout=10)

            deadline = time.monotonic() + self._timeout
            while time.monotonic() < deadline:
                try:
                    r = redis_lib.Redis(
                        host=self._redis_host,
                        port=self._redis_port,
                        socket_timeout=3,
                        socket_connect_timeout=3,
                    )
                    r.ping()
                    r.close()
                    logger.info("RestartRedisStrategy: Redis is responding to PING")
                    return RecoveryResult(
                        success=True,
                        strategy_name=self.name,
                        message="Redis restarted and is responding to PING.",
                        attempt=incident.retry_count + 1,
                    )
                except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
                    time.sleep(2)

            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"Redis did not respond to PING within {self._timeout}s.",
                attempt=incident.retry_count + 1,
                error="timeout",
            )
        except Exception as exc:
            logger.exception("RestartRedisStrategy: error: %s", exc)
            return RecoveryResult(
                success=False,
                strategy_name=self.name,
                message=f"Redis restart failed: {exc}",
                attempt=incident.retry_count + 1,
                error=str(exc),
            )
