"""
Phoenix Agent — System Collector Plugin

Collects host-level system metrics using psutil:
- Overall CPU usage
- Overall memory usage

Used as a supplementary signal alongside container-level metrics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import psutil

from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)


class SystemCollector:
    """
    Host-level system metrics collector.

    Provides overall CPU and memory usage of the Docker host.
    Useful for detecting host-level resource exhaustion that may
    affect multiple containers simultaneously.
    """

    name: str = "system:host"
    service: str = "host"

    def __init__(self, container_name: str = "host") -> None:
        self.container_name = container_name

    def collect(self) -> ServiceSnapshot:
        """Collect host system metrics via psutil. Never raises."""
        cpu_percent = 0.0
        memory_percent = 0.0
        memory_mb = 0.0

        try:
            cpu_percent = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            memory_percent = mem.percent
            memory_mb = mem.used / (1024 * 1024)
        except Exception as exc:
            logger.exception("SystemCollector: error collecting host metrics: %s", exc)

        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status="running",
            cpu_percent=round(cpu_percent, 2),
            memory_percent=round(memory_percent, 2),
            memory_mb=round(memory_mb, 2),
            collected_at=datetime.now(timezone.utc),
        )

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.cpu_percent < 95.0 and snapshot.memory_percent < 95.0
