"""
Phoenix Agent — Container Detection Rules

Rules for detecting container-level failures:
- ContainerDownRule: container not in 'running' state
- RepeatedRestartRule: restart count delta exceeds threshold
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


class ContainerDownRule(DetectionRule):
    """Detects when a container is not in the 'running' state."""

    name = "ContainerDownRule"

    _NON_RUNNING_STATUSES = {"exited", "dead", "not_found", "error", "api_error"}

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.container_status in self._NON_RUNNING_STATUSES

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.CONTAINER_DOWN,
            severity=Severity.CRITICAL,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=(
                f"Container '{snapshot.container_name}' is not running. "
                f"Status: {snapshot.container_status}"
            ),
            metadata={"container_status": snapshot.container_status},
        )
        return incident


class RepeatedRestartRule(DetectionRule):
    """
    Detects containers that are crash-looping.

    Stateless: compares restart_count against a threshold.
    A restart count > threshold is treated as a repeated-restart incident.
    """

    name = "RepeatedRestartRule"

    def __init__(self, restart_threshold: int = 3) -> None:
        self._threshold = restart_threshold

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.restart_count >= self._threshold

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.REPEATED_RESTARTS,
            severity=Severity.HIGH,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=(
                f"Container '{snapshot.container_name}' has restarted "
                f"{snapshot.restart_count} time(s) — possible crash loop."
            ),
            metadata={"restart_count": snapshot.restart_count},
        )
        return incident
