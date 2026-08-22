"""
Phoenix Agent — Redis Collector Plugin

Tests Redis connectivity using redis-py.
Records: reachability, PING response time.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import redis
import redis.exceptions

from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)


class RedisCollector:
    """
    Collector plugin for Redis connectivity monitoring.

    Performs a lightweight PING command to verify Redis is accepting connections.
    Creates a new connection per poll to avoid stale connection state.
    """

    name: str
    service: str

    def __init__(
        self,
        service: str,
        container_name: str,
        host: str,
        port: int,
        socket_timeout: float = 3.0,
    ) -> None:
        self.service = service
        self.container_name = container_name
        self.name = f"redis:{service}"
        self._host = host
        self._port = port
        self._socket_timeout = socket_timeout

    def collect(self) -> ServiceSnapshot:
        """Ping Redis and record the result. Never raises."""
        redis_reachable = False
        latency_ms: Optional[float] = None

        try:
            client = redis.Redis(
                host=self._host,
                port=self._port,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_timeout,
            )
            start = time.monotonic()
            client.ping()
            latency_ms = (time.monotonic() - start) * 1000
            redis_reachable = True
            client.close()
            logger.debug("RedisCollector[%s]: reachable (%.1fms)", self.service, latency_ms)
        except redis.exceptions.ConnectionError as exc:
            logger.warning("RedisCollector[%s]: connection refused — %s", self.service, exc)
        except redis.exceptions.TimeoutError:
            logger.warning("RedisCollector[%s]: timeout after %.1fs", self.service, self._socket_timeout)
        except Exception as exc:
            logger.exception("RedisCollector[%s]: unexpected error: %s", self.service, exc)

        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status="unknown",
            redis_reachable=redis_reachable,
            health_latency_ms=latency_ms,
            collected_at=datetime.now(timezone.utc),
        )

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.redis_reachable is True
