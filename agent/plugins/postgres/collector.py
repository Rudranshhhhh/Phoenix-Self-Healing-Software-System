"""
Phoenix Agent — PostgreSQL Collector Plugin

Tests PostgreSQL connectivity via psycopg2.
Records: reachability, response time, basic query validation.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)


class PostgresCollector:
    """
    Collector plugin for PostgreSQL connectivity monitoring.

    Performs a lightweight connection test using psycopg2.
    Does NOT depend on SQLAlchemy — raw driver for minimal overhead.
    """

    name: str
    service: str

    def __init__(
        self,
        service: str,
        container_name: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        connect_timeout: int = 5,
    ) -> None:
        self.service = service
        self.container_name = container_name
        self.name = f"postgres:{service}"
        self._dsn = (
            f"host={host} port={port} user={user} "
            f"password={password} dbname={database} "
            f"connect_timeout={connect_timeout}"
        )

    def collect(self) -> ServiceSnapshot:
        """Attempt a PostgreSQL connection and record the result. Never raises."""
        db_reachable = False
        latency_ms: Optional[float] = None

        try:
            start = time.monotonic()
            conn = psycopg2.connect(self._dsn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            latency_ms = (time.monotonic() - start) * 1000
            db_reachable = True
            logger.debug("PostgresCollector[%s]: reachable (%.1fms)", self.service, latency_ms)
        except psycopg2.OperationalError as exc:
            logger.warning("PostgresCollector[%s]: unreachable — %s", self.service, exc)
        except Exception as exc:
            logger.exception("PostgresCollector[%s]: unexpected error: %s", self.service, exc)

        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status="unknown",
            db_reachable=db_reachable,
            health_latency_ms=latency_ms,
            collected_at=datetime.now(timezone.utc),
        )

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.db_reachable is True
