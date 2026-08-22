"""
Phoenix Agent — Escalation Engine

Subscribes to ESCALATION_TRIGGERED on the EventBus.
Marks the incident as ESCALATED (CRITICAL severity).
Notifies the Reporter for immediate dashboard alert.

Escalation means: Phoenix has exhausted all automated recovery options.
Human intervention is required.
"""
from __future__ import annotations

import logging

from agent.events.bus import EventBus
from agent.events.event_types import ESCALATION_TRIGGERED, INCIDENT_RESOLVED
from agent.events.incident import Incident, IncidentPhase

logger = logging.getLogger(__name__)


class EscalationEngine:
    """
    Handles incidents that could not be automatically recovered.

    Subscribes to: ESCALATION_TRIGGERED
    Side effects:
    - Marks incident as ESCALATED + CRITICAL
    - Adds ESCALATED phase to timeline
    - Re-publishes incident for Reporter to send critical dashboard alert
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(ESCALATION_TRIGGERED, self.on_escalation)
        logger.info("EscalationEngine: initialised")

    def on_escalation(self, incident: Incident) -> None:
        """
        Handle an escalation event.
        Marks incident critical and notifies the reporter.
        """
        logger.critical(
            "EscalationEngine: 🚨 ESCALATION — service '%s' could not be recovered "
            "after %d attempts. Incident: %s",
            incident.service,
            incident.retry_count,
            incident.incident_id,
        )

        incident.mark_escalated()
        incident.add_timeline_event(
            phase=IncidentPhase.ESCALATED,
            message=(
                f"Automatic recovery failed after {incident.retry_count} attempt(s). "
                "Human intervention required."
            ),
            metadata={
                "retry_count": incident.retry_count,
                "last_strategy": incident.recovery_strategy,
            },
        )

        # Re-publish as INCIDENT_RESOLVED so Reporter captures final state.
        # The ESCALATED status in the incident document signals human attention needed.
        self._bus.publish(INCIDENT_RESOLVED, incident)
        logger.info(
            "EscalationEngine: escalation published for incident '%s'",
            incident.incident_id,
        )
