"""
Phoenix Agent — Reporter Service

Facade that subscribes to terminal EventBus events and dispatches
to both HTTP and WebSocket reporters.

Terminal events (incidents that have reached their final state):
  - INCIDENT_RESOLVED  → report_incident (resolved or escalated)
  - SNAPSHOT_COLLECTED → report_metric (every snapshot)

Design: The ReporterService has no business logic. It routes events
to reporters. Adding a new reporter (e.g. Slack, PagerDuty) = adding
one line here and one new reporter class.
"""
from __future__ import annotations

import logging

from agent.events.bus import EventBus
from agent.events.event_types import (
    INCIDENT_RESOLVED,
    RECOVERY_STARTED,
    SNAPSHOT_COLLECTED,
)
from agent.events.incident import Incident, ServiceSnapshot
from agent.reporters.http_reporter import HTTPReporter
from agent.reporters.websocket_reporter import WebSocketReporter

logger = logging.getLogger(__name__)


class ReporterService:
    """
    Subscribes to EventBus events and dispatches to all registered reporters.
    """

    def __init__(
        self,
        bus: EventBus,
        http_reporter: HTTPReporter,
        ws_reporter: WebSocketReporter,
    ) -> None:
        self._http = http_reporter
        self._ws = ws_reporter

        # Subscribe to events of interest
        bus.subscribe(INCIDENT_RESOLVED, self._on_incident_resolved)
        bus.subscribe(RECOVERY_STARTED, self._on_recovery_started)
        bus.subscribe(SNAPSHOT_COLLECTED, self._on_snapshot_collected)

        logger.info("ReporterService: initialised and subscribed to EventBus")

    def _on_incident_resolved(self, incident: Incident) -> None:
        """Report final incident state (resolved or escalated)."""
        logger.info(
            "ReporterService: reporting incident '%s' (status=%s)",
            incident.incident_id, incident.status.value,
        )
        self._http.report_incident(incident)
        self._ws.report_incident(incident)

    def _on_recovery_started(self, incident: Incident) -> None:
        """Report real-time recovery-started update to dashboard."""
        self._ws.report_incident(incident)

    def _on_snapshot_collected(self, snapshot: ServiceSnapshot) -> None:
        """
        Report metrics snapshot for time-series storage.
        Only report Docker snapshots (those with CPU/memory data) to reduce noise.
        """
        if snapshot.cpu_percent > 0 or snapshot.memory_percent > 0:
            self._http.report_metric(snapshot)
            self._ws.report_metric(snapshot)
