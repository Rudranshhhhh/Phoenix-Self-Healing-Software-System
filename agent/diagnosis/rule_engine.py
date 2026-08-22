"""
Phoenix Agent — Diagnosis Rule Engine

Maps FailureType → (root_cause, confidence_score).

Design:
- Pure function — no side effects, no external dependencies.
- Rules dict is the single source of truth for deterministic diagnosis.
- Confidence scores reflect how certain we are about the root cause
  given the failure type alone (before log analysis or AI enrichment).
- Easily extended: add a new FailureType entry to the dict.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent.events.incident import FailureType


@dataclass(frozen=True)
class DiagnosisResult:
    """Result of a deterministic rule-based diagnosis."""
    root_cause: str
    confidence: float  # 0.0 – 1.0


# ============================================================================ #
# Diagnosis Rules                                                               #
# ============================================================================ #

_RULES: dict[FailureType, DiagnosisResult] = {
    FailureType.CONTAINER_DOWN: DiagnosisResult(
        root_cause=(
            "The container process has exited unexpectedly. "
            "Common causes: unhandled exception, OOM kill, or manual stop."
        ),
        confidence=0.97,
    ),
    FailureType.HIGH_CPU: DiagnosisResult(
        root_cause=(
            "CPU usage is abnormally high. "
            "Possible causes: infinite loop, inefficient query, or sudden traffic spike."
        ),
        confidence=0.82,
    ),
    FailureType.HIGH_MEMORY: DiagnosisResult(
        root_cause=(
            "Memory consumption is approaching the container limit. "
            "Possible causes: memory leak, large in-memory cache, or unbound data growth."
        ),
        confidence=0.85,
    ),
    FailureType.DATABASE_UNREACHABLE: DiagnosisResult(
        root_cause=(
            "PostgreSQL is not accepting connections. "
            "Possible causes: database container exited, network partition, or exhausted connection pool."
        ),
        confidence=0.95,
    ),
    FailureType.REDIS_DOWN: DiagnosisResult(
        root_cause=(
            "Redis is not responding to PING. "
            "Possible causes: Redis container stopped, OOM eviction, or network issue."
        ),
        confidence=0.94,
    ),
    FailureType.HEALTH_ENDPOINT_FAILURE: DiagnosisResult(
        root_cause=(
            "The application health endpoint is returning an error or timing out. "
            "Possible causes: application startup failure, deadlock, or dependency unavailable."
        ),
        confidence=0.88,
    ),
    FailureType.REPEATED_RESTARTS: DiagnosisResult(
        root_cause=(
            "The container is in a crash-restart loop. "
            "Possible causes: misconfiguration, missing environment variable, or dependency not ready."
        ),
        confidence=0.91,
    ),
    FailureType.UNKNOWN: DiagnosisResult(
        root_cause="Failure type could not be determined. Manual inspection required.",
        confidence=0.30,
    ),
}


def diagnose(failure_type: FailureType) -> DiagnosisResult:
    """
    Return a DiagnosisResult for the given FailureType.

    Falls back to UNKNOWN if the failure type is not in the rules dict.
    This is a pure function — no mutations, no external calls.
    """
    return _RULES.get(failure_type, _RULES[FailureType.UNKNOWN])
