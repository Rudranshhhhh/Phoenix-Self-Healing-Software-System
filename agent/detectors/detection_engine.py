"""
Phoenix Agent — Detection Engine

Subscribes to SNAPSHOT_COLLECTED events on the EventBus.
Evaluates each snapshot against all registered rules.
Publishes INCIDENT_DETECTED for each matched rule.

Design:
- Stateless evaluation — no stored state between snapshots.
- Rules are evaluated in priority order (defined by registration).
- One snapshot can trigger multiple incidents (e.g. down container + high restarts).
- Deduplication is handled upstream by the backend IncidentService.
"""
from __future__ import annotations

import logging

from agent.detectors.rules.base import DetectionRule
from agent.events.bus import EventBus
from agent.events.event_types import INCIDENT_DETECTED, SNAPSHOT_COLLECTED
from agent.events.incident import ServiceSnapshot

logger = logging.getLogger(__name__)


class DetectionEngine:
    """
    Evaluates ServiceSnapshots against registered detection rules.

    Subscribes to SNAPSHOT_COLLECTED on the EventBus.
    Publishes INCIDENT_DETECTED for each matching rule.
    """

    def __init__(self, bus: EventBus, rules: list[DetectionRule]) -> None:
        self._bus = bus
        self._rules = rules
        bus.subscribe(SNAPSHOT_COLLECTED, self.on_snapshot)
        logger.info(
            "DetectionEngine: initialised with %d rule(s): %s",
            len(rules), [r.name for r in rules],
        )

    def on_snapshot(self, snapshot: ServiceSnapshot) -> None:
        """
        Called by EventBus for every SNAPSHOT_COLLECTED event.
        Evaluates all rules and publishes incidents for matches.
        """
        for rule in self._rules:
            try:
                if rule.matches(snapshot):
                    incident = rule.create_incident(snapshot)
                    logger.warning(
                        "DetectionEngine: [%s] rule '%s' matched for service '%s'",
                        incident.failure_type.value,
                        rule.name,
                        snapshot.service,
                    )
                    self._bus.publish(INCIDENT_DETECTED, incident)
            except Exception:
                logger.exception(
                    "DetectionEngine: rule '%s' raised an exception on snapshot from '%s'",
                    rule.name, snapshot.service,
                )

    @property
    def rule_names(self) -> list[str]:
        return [r.name for r in self._rules]
