"""
Phoenix Agent — Resource Detection Rules

Rules for detecting resource exhaustion:
- HighCPURule: CPU usage exceeds threshold
- HighMemoryRule: Memory usage exceeds threshold
"""
from __future__ import annotations

from agent.detectors.rules.base import DetectionRule
from agent.events.incident import (
    FailureType,
    Incident,
    IncidentPhase,
    Severity,
    ServiceSnapshot,
)


class HighCPURule(DetectionRule):
    """Detects sustained high CPU usage."""

    name = "HighCPURule"

    def __init__(self, threshold_percent: float = 85.0) -> None:
        self._threshold = threshold_percent

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.cpu_percent >= self._threshold

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.HIGH_CPU,
            severity=Severity.HIGH,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=(
                f"High CPU detected on '{snapshot.container_name}': "
                f"{snapshot.cpu_percent:.1f}% (threshold: {self._threshold}%)"
            ),
            metadata={"cpu_percent": snapshot.cpu_percent, "threshold": self._threshold},
        )
        return incident


class HighMemoryRule(DetectionRule):
    """Detects high memory usage."""

    name = "HighMemoryRule"

    def __init__(self, threshold_percent: float = 90.0) -> None:
        self._threshold = threshold_percent

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.memory_percent >= self._threshold

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.HIGH_MEMORY,
            severity=Severity.HIGH,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=(
                f"High memory detected on '{snapshot.container_name}': "
                f"{snapshot.memory_percent:.1f}% ({snapshot.memory_mb:.0f} MB) "
                f"(threshold: {self._threshold}%)"
            ),
            metadata={
                "memory_percent": snapshot.memory_percent,
                "memory_mb": snapshot.memory_mb,
                "threshold": self._threshold,
            },
        )
        return incident
