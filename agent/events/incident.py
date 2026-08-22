"""
Phoenix Agent — Domain Model

This module defines the canonical Incident object and all related types.
It has ZERO external dependencies — pure Python dataclasses and enums.

All other modules communicate via these types. This is the innermost ring
of the Clean Architecture onion.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ============================================================================ #
# Enumerations                                                                  #
# ============================================================================ #

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FailureType(str, Enum):
    CONTAINER_DOWN = "CONTAINER_DOWN"
    HIGH_CPU = "HIGH_CPU"
    HIGH_MEMORY = "HIGH_MEMORY"
    DATABASE_UNREACHABLE = "DATABASE_UNREACHABLE"
    REDIS_DOWN = "REDIS_DOWN"
    HEALTH_ENDPOINT_FAILURE = "HEALTH_ENDPOINT_FAILURE"
    REPEATED_RESTARTS = "REPEATED_RESTARTS"
    UNKNOWN = "UNKNOWN"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    DIAGNOSING = "DIAGNOSING"
    RECOVERING = "RECOVERING"
    VERIFYING = "VERIFYING"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class IncidentPhase(str, Enum):
    """Phases recorded in the incident timeline."""
    DETECTED = "DETECTED"
    DIAGNOSED = "DIAGNOSED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


# ============================================================================ #
# Value Objects                                                                 #
# ============================================================================ #

@dataclass
class ServiceSnapshot:
    """
    A point-in-time snapshot of a monitored service's health metrics.
    Captured by collectors and embedded inside Incidents.
    """
    service: str
    container_name: str
    container_status: str               # running | exited | paused | etc.
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    restart_count: int = 0
    health_status: Optional[str] = None  # healthy | unhealthy | None
    health_latency_ms: Optional[float] = None
    db_reachable: Optional[bool] = None
    redis_reachable: Optional[bool] = None
    log_errors: list[str] = field(default_factory=list)
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "container_name": self.container_name,
            "container_status": self.container_status,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_mb": self.memory_mb,
            "restart_count": self.restart_count,
            "health_status": self.health_status,
            "health_latency_ms": self.health_latency_ms,
            "db_reachable": self.db_reachable,
            "redis_reachable": self.redis_reachable,
            "log_errors": self.log_errors,
            "collected_at": self.collected_at.isoformat(),
        }


@dataclass
class TimelineEvent:
    """
    A single recorded event in an Incident's lifecycle.
    Stored as an embedded array inside the Incident document.
    """
    phase: IncidentPhase
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class RecoveryResult:
    """Result returned by a RecoveryStrategy after execution."""
    success: bool
    strategy_name: str
    message: str
    attempt: int = 1
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "strategy_name": self.strategy_name,
            "message": self.message,
            "attempt": self.attempt,
            "error": self.error,
        }


# ============================================================================ #
# Incident — The Canonical Domain Object                                        #
# ============================================================================ #

@dataclass
class Incident:
    """
    The canonical domain object representing a detected failure lifecycle.

    All Phoenix modules communicate via Incident objects.
    This class has zero external dependencies — it is the innermost ring
    of the Clean Architecture onion.

    Timeline is embedded as an ordered list of TimelineEvent objects.
    Metrics snapshot is captured at detection time and embedded.
    """

    service: str
    container_name: str
    failure_type: FailureType
    severity: Severity
    metrics_snapshot: ServiceSnapshot

    # Auto-generated fields
    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: IncidentStatus = IncidentStatus.DETECTED
    confidence_score: float = 0.0              # 0.0 – 1.0

    # Timestamps
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    diagnosed_at: Optional[datetime] = None
    recovery_started_at: Optional[datetime] = None
    verification_completed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    # Diagnosis
    root_cause: str = ""
    grok_summary: Optional[str] = None
    grok_recommendations: Optional[list[str]] = None

    # Recovery
    recovery_strategy: Optional[str] = None
    retry_count: int = 0
    resolved: bool = False

    # Timeline — ordered list of phase events
    timeline: list[TimelineEvent] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Lifecycle Helpers                                                    #
    # ------------------------------------------------------------------ #

    def add_timeline_event(
        self,
        phase: IncidentPhase,
        message: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Append a new phase event to the incident timeline."""
        self.timeline.append(
            TimelineEvent(
                phase=phase,
                message=message,
                metadata=metadata or {},
            )
        )

    def mark_diagnosing(self) -> None:
        self.status = IncidentStatus.DIAGNOSING
        self.diagnosed_at = datetime.now(timezone.utc)

    def mark_recovering(self, strategy_name: str) -> None:
        self.status = IncidentStatus.RECOVERING
        self.recovery_started_at = datetime.now(timezone.utc)
        self.recovery_strategy = strategy_name

    def mark_verifying(self) -> None:
        self.status = IncidentStatus.VERIFYING

    def mark_resolved(self) -> None:
        self.status = IncidentStatus.RESOLVED
        self.resolved = True
        self.resolved_at = datetime.now(timezone.utc)
        self.verification_completed_at = datetime.now(timezone.utc)

    def mark_escalated(self) -> None:
        self.status = IncidentStatus.ESCALATED
        self.severity = Severity.CRITICAL

    def increment_retry(self) -> None:
        self.retry_count += 1

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        """Serialise to a MongoDB-ready dict."""
        return {
            "incident_id": self.incident_id,
            "service": self.service,
            "container_name": self.container_name,
            "failure_type": self.failure_type.value,
            "severity": self.severity.value,
            "confidence_score": self.confidence_score,
            "status": self.status.value,
            "root_cause": self.root_cause,
            "grok_summary": self.grok_summary,
            "grok_recommendations": self.grok_recommendations,
            "metrics_snapshot": self.metrics_snapshot.to_dict(),
            "recovery_strategy": self.recovery_strategy,
            "retry_count": self.retry_count,
            "resolved": self.resolved,
            "detected_at": self.detected_at.isoformat(),
            "diagnosed_at": self.diagnosed_at.isoformat() if self.diagnosed_at else None,
            "recovery_started_at": self.recovery_started_at.isoformat() if self.recovery_started_at else None,
            "verification_completed_at": self.verification_completed_at.isoformat() if self.verification_completed_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "timeline": [e.to_dict() for e in self.timeline],
        }
