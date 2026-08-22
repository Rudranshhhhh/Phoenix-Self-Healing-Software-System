"""
Phoenix Agent — Service Detection Rules

Rules for detecting service connectivity failures:
- DatabaseUnreachableRule
- RedisDownRule
- HealthEndpointFailureRule
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


class DatabaseUnreachableRule(DetectionRule):
    """Detects when PostgreSQL connectivity check fails."""

    name = "DatabaseUnreachableRule"

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.db_reachable is False

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.DATABASE_UNREACHABLE,
            severity=Severity.CRITICAL,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=f"PostgreSQL is unreachable for service '{snapshot.service}'.",
            metadata={"db_reachable": False},
        )
        return incident


class RedisDownRule(DetectionRule):
    """Detects when Redis connectivity check fails."""

    name = "RedisDownRule"

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        return snapshot.redis_reachable is False

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.REDIS_DOWN,
            severity=Severity.HIGH,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=f"Redis is unreachable for service '{snapshot.service}'.",
            metadata={"redis_reachable": False},
        )
        return incident


class HealthEndpointFailureRule(DetectionRule):
    """
    Detects health endpoint failures.

    Triggers on:
    - health_status == "unhealthy"
    - health_latency_ms exceeds threshold
    """

    name = "HealthEndpointFailureRule"

    def __init__(self, latency_threshold_ms: float = 5000.0) -> None:
        self._latency_threshold = latency_threshold_ms

    def matches(self, snapshot: ServiceSnapshot) -> bool:
        if snapshot.health_status == "unhealthy":
            return True
        if (
            snapshot.health_latency_ms is not None
            and snapshot.health_latency_ms > self._latency_threshold
        ):
            return True
        return False

    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        if snapshot.health_latency_ms and snapshot.health_latency_ms > self._latency_threshold:
            msg = (
                f"Health endpoint slow on '{snapshot.service}': "
                f"{snapshot.health_latency_ms:.0f}ms (threshold: {self._latency_threshold:.0f}ms)"
            )
        else:
            msg = f"Health endpoint unhealthy on '{snapshot.service}'."

        incident = Incident(
            service=snapshot.service,
            container_name=snapshot.container_name,
            failure_type=FailureType.HEALTH_ENDPOINT_FAILURE,
            severity=Severity.HIGH,
            metrics_snapshot=snapshot,
        )
        incident.add_timeline_event(
            phase=IncidentPhase.DETECTED,
            message=msg,
            metadata={
                "health_status": snapshot.health_status,
                "health_latency_ms": snapshot.health_latency_ms,
            },
        )
        return incident
