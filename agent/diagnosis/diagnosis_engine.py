"""
Phoenix Agent — Diagnosis Engine

Subscribes to INCIDENT_DETECTED on the EventBus.
Pipeline:
  1. RuleEngine → sets root_cause + confidence_score (deterministic, instant)
  2. AIAdvisor  → sets grok_summary + grok_recommendations (async, degradable)

Publishes INCIDENT_DIAGNOSED when complete.

Design:
- The AI Advisor is optional — if Grok is disabled or times out,
  the incident is still published with the rule-based diagnosis.
- Diagnosis never performs recovery. It only enriches the Incident.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.diagnosis import rule_engine
from agent.events.bus import EventBus
from agent.events.event_types import INCIDENT_DETECTED, INCIDENT_DIAGNOSED
from agent.events.incident import Incident, IncidentPhase, IncidentStatus

logger = logging.getLogger(__name__)


class DiagnosisEngine:
    """
    Enriches Incidents with root cause and AI-generated summaries.

    Subscribes to: INCIDENT_DETECTED
    Publishes: INCIDENT_DIAGNOSED
    """

    def __init__(self, bus: EventBus, ai_advisor=None) -> None:
        """
        Args:
            bus: The application EventBus.
            ai_advisor: Optional AIAdvisor instance. If None, AI enrichment is skipped.
        """
        self._bus = bus
        self._ai_advisor = ai_advisor
        bus.subscribe(INCIDENT_DETECTED, self.on_incident_detected)
        logger.info(
            "DiagnosisEngine: initialised (AI advisor: %s)",
            "enabled" if ai_advisor else "disabled",
        )

    def on_incident_detected(self, incident: Incident) -> None:
        """
        Triggered by INCIDENT_DETECTED.
        Runs rule-based diagnosis, then AI enrichment, then publishes.
        """
        incident.mark_diagnosing()

        # Step 1: Deterministic rule-based diagnosis
        try:
            result = rule_engine.diagnose(incident.failure_type)
            incident.root_cause = result.root_cause
            incident.confidence_score = result.confidence
            logger.info(
                "DiagnosisEngine: [%s] root_cause='%s...' confidence=%.0f%%",
                incident.service,
                incident.root_cause[:60],
                result.confidence * 100,
            )
        except Exception:
            logger.exception(
                "DiagnosisEngine: rule engine failed for '%s'", incident.service
            )
            incident.root_cause = "Diagnosis failed — manual inspection required."
            incident.confidence_score = 0.0

        incident.add_timeline_event(
            phase=IncidentPhase.DIAGNOSED,
            message=(
                f"Root cause identified with {incident.confidence_score * 100:.0f}% confidence: "
                f"{incident.root_cause}"
            ),
            metadata={
                "confidence_score": incident.confidence_score,
                "root_cause": incident.root_cause,
            },
        )
        incident.diagnosed_at = datetime.now(timezone.utc)

        # Step 2: AI enrichment (optional, non-blocking)
        if self._ai_advisor is not None:
            try:
                incident = self._ai_advisor.enrich(incident)
            except Exception:
                logger.exception(
                    "DiagnosisEngine: AI advisor failed for '%s' — proceeding without AI summary",
                    incident.service,
                )

        self._bus.publish(INCIDENT_DIAGNOSED, incident)
        logger.info(
            "DiagnosisEngine: published INCIDENT_DIAGNOSED for '%s' (%s)",
            incident.service, incident.incident_id,
        )
