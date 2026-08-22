"""
Phoenix Agent — HTTP Health Collector Plugin

Polls an HTTP health endpoint and records status code, latency, and body.
Used to detect HealthEndpointFailure incidents.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests
import requests.exceptions

from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)


class HealthCollector:
    """
    Collector plugin for HTTP health endpoint monitoring.

    Polls the configured URL and records:
    - HTTP status code
    - Response latency (ms)
    - Whether the endpoint returned a healthy response
    """

    name: str
    service: str

    def __init__(
        self,
        service: str,
        health_url: str,
        container_name: str,
        timeout_seconds: float = 5.0,
        healthy_status_codes: Optional[list[int]] = None,
    ) -> None:
        self.service = service
        self.health_url = health_url
        self.container_name = container_name
        self.name = f"health:{service}"
        self._timeout = timeout_seconds
        self._healthy_codes = set(healthy_status_codes or [200])

    def collect(self) -> ServiceSnapshot:
        """Poll the health endpoint. Never raises."""
        health_status = "unknown"
        latency_ms: Optional[float] = None

        try:
            start = time.monotonic()
            response = requests.get(self.health_url, timeout=self._timeout)
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code in self._healthy_codes:
                health_status = "healthy"
            else:
                health_status = "unhealthy"
                logger.warning(
                    "HealthCollector[%s]: status %d from %s",
                    self.service, response.status_code, self.health_url,
                )

        except requests.exceptions.Timeout:
            logger.warning("HealthCollector[%s]: timeout after %.1fs", self.service, self._timeout)
            health_status = "unhealthy"
        except requests.exceptions.ConnectionError:
            logger.warning("HealthCollector[%s]: connection refused to %s", self.service, self.health_url)
            health_status = "unhealthy"
        except Exception as exc:
            logger.exception("HealthCollector[%s]: unexpected error: %s", self.service, exc)
            health_status = "unhealthy"

        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status="unknown",  # health collector doesn't query Docker
            health_status=health_status,
            health_latency_ms=latency_ms,
            collected_at=datetime.now(timezone.utc),
        )

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.health_status == "healthy"
