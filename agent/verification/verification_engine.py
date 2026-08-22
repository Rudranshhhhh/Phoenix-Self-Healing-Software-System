"""
Phoenix Agent — Verification Engine

Subscribes to RECOVERY_FINISHED on the EventBus.
Re-collects a snapshot and verifies the service is healthy.

Verification flow:
  RECOVERY_FINISHED
  → re-collect snapshot
  → run verification checks
  → PASS: publish VerificationPassed → IncidentResolved
  → FAIL: retry_count < threshold?
           YES → publish INCIDENT_DIAGNOSED (re-enter recovery loop)
           NO  → publish EscalationTriggered
"""
from __future__ import annotations

import logging
import time

from agent.events.bus import EventBus
from agent.events.event_types import (
    ESCALATION_TRIGGERED,
    INCIDENT_DIAGNOSED,
    INCIDENT_RESOLVED,
    RECOVERY_FAILED,
    RECOVERY_FINISHED,
    VERIFICATION_FAILED,
    VERIFICATION_PASSED,
)
from agent.events.incident import Incident, IncidentPhase
from agent.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


class VerificationEngine:
    """
    Verifies service health after a recovery attempt.

    Subscribes to: RECOVERY_FINISHED, RECOVERY_FAILED
    Publishes: VERIFICATION_PASSED, VERIFICATION_FAILED,
               INCIDENT_RESOLVED, ESCALATION_TRIGGERED, INCIDENT_DIAGNOSED
    """

    def __init__(
        self,
        bus: EventBus,
        registry: PluginRegistry,
        escalation_threshold: int = 3,
        verify_wait_seconds: float = 5.0,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._threshold = escalation_threshold
        self._wait = verify_wait_seconds

        bus.subscribe(RECOVERY_FINISHED, self.on_recovery_finished)
        bus.subscribe(RECOVERY_FAILED, self.on_recovery_failed)
        logger.info(
            "VerificationEngine: initialised (threshold=%d retries)", escalation_threshold
        )

    def on_recovery_finished(self, incident: Incident) -> None:
        """Verify after a successful recovery strategy execution."""
        logger.info(
            "VerificationEngine: verifying service '%s' after recovery",
            incident.service,
        )
        incident.mark_verifying()
        time.sleep(self._wait)  # allow container to stabilise
        self._verify(incident)

    def on_recovery_failed(self, incident: Incident) -> None:
        """Handle retry or escalation after a failed recovery attempt."""
        if incident.retry_count < self._threshold:
            logger.info(
                "VerificationEngine: retry %d/%d for '%s'",
                incident.retry_count, self._threshold, incident.service,
            )
            # Re-enter recovery loop
            self._bus.publish(INCIDENT_DIAGNOSED, incident)
        else:
            logger.warning(
                "VerificationEngine: escalating '%s' after %d failed attempts",
                incident.service, incident.retry_count,
            )
            self._bus.publish(ESCALATION_TRIGGERED, incident)

    def _verify(self, incident: Incident) -> None:
        """Run collector-based health check and publish result."""
        collector_name = f"docker:{incident.service}"
        health_collector_name = f"health:{incident.service}"

        passed = False
        message = "Verification failed — service still unhealthy."

        # Try docker collector first
        try:
            if collector_name in self._registry:
                collector = self._registry.get(collector_name)
                snapshot = collector.collect()
                if collector.is_healthy(snapshot):
                    passed = True
                    message = f"Container '{incident.container_name}' verified running."
        except Exception:
            logger.exception("VerificationEngine: docker check error for '%s'", incident.service)

        # If docker healthy, also check health endpoint
        if passed and health_collector_name in self._registry:
            try:
                health_col = self._registry.get(health_collector_name)
                health_snap = health_col.collect()
                if not health_col.is_healthy(health_snap):
                    passed = False
                    message = "Container running but health endpoint still failing."
            except Exception:
                logger.exception(
                    "VerificationEngine: health endpoint check error for '%s'", incident.service
                )

        if passed:
            incident.mark_resolved()
            incident.add_timeline_event(
                phase=IncidentPhase.VERIFIED,
                message=message,
            )
            incident.add_timeline_event(
                phase=IncidentPhase.RESOLVED,
                message=f"Incident resolved for service '{incident.service}'.",
            )
            self._bus.publish(VERIFICATION_PASSED, incident)
            self._bus.publish(INCIDENT_RESOLVED, incident)
            logger.info(
                "VerificationEngine: ✓ incident '%s' RESOLVED", incident.incident_id
            )
        else:
            incident.add_timeline_event(
                phase=IncidentPhase.VERIFICATION_FAILED,
                message=message,
            )
            self._bus.publish(VERIFICATION_FAILED, incident)

            if incident.retry_count < self._threshold:
                logger.info(
                    "VerificationEngine: verification failed — re-entering recovery (retry %d/%d)",
                    incident.retry_count, self._threshold,
                )
                self._bus.publish(INCIDENT_DIAGNOSED, incident)
            else:
                logger.warning(
                    "VerificationEngine: verification failed %d times — escalating '%s'",
                    incident.retry_count, incident.service,
                )
                self._bus.publish(ESCALATION_TRIGGERED, incident)
