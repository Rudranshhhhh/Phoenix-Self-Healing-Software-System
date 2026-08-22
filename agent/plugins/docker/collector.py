"""
Phoenix Agent — Docker Collector Plugin

Collects: container status, CPU%, memory%, restart count.
Uses the official Docker SDK for Python.

Design: Never raises — all exceptions are caught and reflected
in the snapshot so the pipeline continues uninterrupted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import docker
import docker.errors
from docker.models.containers import Container

from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)


class DockerCollector:
    """
    Collector plugin for Docker container metrics.

    Each instance monitors one container. Multiple instances can be
    registered in the PluginRegistry for multi-service monitoring.
    """

    name: str
    service: str

    def __init__(self, service: str, container_name: str, docker_socket: str) -> None:
        self.service = service
        self.container_name = container_name
        self.name = f"docker:{service}"
        self._socket = docker_socket
        self._client: Optional[docker.DockerClient] = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._socket)
        return self._client

    def collect(self) -> ServiceSnapshot:
        """Collect Docker container metrics. Never raises."""
        try:
            client = self._get_client()
            container: Container = client.containers.get(self.container_name)
            return self._extract_snapshot(container)
        except docker.errors.NotFound:
            logger.warning("DockerCollector[%s]: container '%s' not found",
                           self.service, self.container_name)
            return self._error_snapshot("not_found")
        except docker.errors.APIError as exc:
            logger.error("DockerCollector[%s]: Docker API error: %s", self.service, exc)
            return self._error_snapshot("api_error")
        except Exception as exc:
            logger.exception("DockerCollector[%s]: unexpected error: %s", self.service, exc)
            return self._error_snapshot("error")

    def _extract_snapshot(self, container: Container) -> ServiceSnapshot:
        """Extract metrics from a live Docker container object."""
        status = container.status  # running | exited | paused | restarting

        cpu_percent = 0.0
        memory_percent = 0.0
        memory_mb = 0.0
        restart_count = 0

        try:
            attrs = container.attrs or {}
            restart_count = attrs.get("RestartCount", 0)

            if status == "running":
                stats = container.stats(stream=False)
                cpu_percent = self._calculate_cpu_percent(stats)
                mem_stats = stats.get("memory_stats", {})
                memory_usage = mem_stats.get("usage", 0)
                memory_limit = mem_stats.get("limit", 1)
                memory_mb = memory_usage / (1024 * 1024)
                memory_percent = (memory_usage / memory_limit) * 100 if memory_limit > 0 else 0.0
        except Exception as exc:
            logger.warning("DockerCollector[%s]: failed to read stats: %s", self.service, exc)

        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status=status,
            cpu_percent=round(cpu_percent, 2),
            memory_percent=round(memory_percent, 2),
            memory_mb=round(memory_mb, 2),
            restart_count=restart_count,
            collected_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _calculate_cpu_percent(stats: dict) -> float:
        """
        Calculate CPU usage percentage from Docker stats payload.
        Uses the delta method as documented in Docker API.
        """
        try:
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"]
                - stats["precpu_stats"]["system_cpu_usage"]
            )
            num_cpus = stats["cpu_stats"].get("online_cpus") or len(
                stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])
            )
            if system_delta > 0:
                return (cpu_delta / system_delta) * num_cpus * 100.0
        except (KeyError, ZeroDivisionError, TypeError):
            pass
        return 0.0

    def _error_snapshot(self, status: str) -> ServiceSnapshot:
        return ServiceSnapshot(
            service=self.service,
            container_name=self.container_name,
            container_status=status,
            collected_at=datetime.now(timezone.utc),
        )

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.container_status == "running"
