"""
Phoenix Agent — Recovery Engine

Subscribes to INCIDENT_DIAGNOSED on the EventBus.
Selects the highest-priority applicable strategy.
Executes it and publishes RECOVERY_FINISHED or RECOVERY_FAILED.

Design:
- Strategy selection is deterministic (sorted by priority, first match wins).
- Recovery never blocks the EventBus thread for long — strategies that
  do blocking waits should be run in their own thread if needed.
- Recovery never makes AI decisions — it is fully rule/strategy driven.
"""
from __future__ import annotations

import logging

from agent.events.bus import EventBus
from agent.events.event_types import (
    INCIDENT_DIAGNOSED,
    RECOVERY_FAILED,
    RECOVERY_FINISHED,
    RECOVERY_STARTED,
)
from agent.events.incident import Incident, IncidentPhase
from agent.recovery.strategies.base import RecoveryStrategy

logger = logging.getLogger(__name__)


class RecoveryEngine:
    """
    Selects and executes recovery strategies for diagnosed incidents.

    Subscribes to: INCIDENT_DIAGNOSED
    Publishes: RECOVERY_STARTED, RECOVERY_FINISHED, RECOVERY_FAILED
    """

    def __init__(self, bus: EventBus, strategies: list[RecoveryStrategy]) -> None:
        self._bus = bus
        self._strategies = sorted(strategies, key=lambda s: s.priority)
        bus.subscribe(INCIDENT_DIAGNOSED, self.on_incident_diagnosed)
        logger.info(
            "RecoveryEngine: initialised with %d strategies: %s",
            len(strategies),
            [s.name for s in self._strategies],
        )

    def on_incident_diagnosed(self, incident: Incident) -> None:
        """
        Called by EventBus when a diagnosed incident is ready for recovery.
        """
        strategy = self._select_strategy(incident)

        if strategy is None:
            logger.warning(
                "RecoveryEngine: no strategy found for FailureType=%s on '%s'",
                incident.failure_type.value, incident.service,
            )
            incident.add_timeline_event(
                phase=IncidentPhase.RECOVERY_FAILED,
                message="No applicable recovery strategy found.",
            )
            self._bus.publish(RECOVERY_FAILED, incident)
            return

        # Mark recovery started
        incident.mark_recovering(strategy.name)
        incident.add_timeline_event(
            phase=IncidentPhase.RECOVERY_STARTED,
            message=f"Executing recovery strategy: {strategy.name}",
            metadata={"strategy": strategy.name, "attempt": incident.retry_count + 1},
        )
        self._bus.publish(RECOVERY_STARTED, incident)

        # Execute strategy
        logger.info(
            "RecoveryEngine: executing '%s' for '%s' (attempt %d)",
            strategy.name, incident.service, incident.retry_count + 1,
        )
        result = strategy.execute(incident)
        incident.increment_retry()

        if result.success:
            incident.add_timeline_event(
                phase=IncidentPhase.RECOVERY_COMPLETED,
                message=result.message,
                metadata=result.to_dict(),
            )
            self._bus.publish(RECOVERY_FINISHED, incident)
        else:
            logger.warning(
                "RecoveryEngine: '%s' failed: %s", strategy.name, result.message
            )
            incident.add_timeline_event(
                phase=IncidentPhase.RECOVERY_FAILED,
                message=result.message,
                metadata=result.to_dict(),
            )
            self._bus.publish(RECOVERY_FAILED, incident)

    def _select_strategy(self, incident: Incident) -> RecoveryStrategy | None:
        """Return the first strategy (by priority) that can handle the incident."""
        for strategy in self._strategies:
            if strategy.can_handle(incident):
                return strategy
        return None
