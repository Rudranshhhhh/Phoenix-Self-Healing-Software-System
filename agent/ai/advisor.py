"""
Phoenix Agent — AI Advisor

The single entry point into the AI Layer.

Responsibilities:
- Enrich incidents with Grok-generated summaries and recommendations
- Degrade gracefully if Grok is unavailable (incident proceeds unchanged)

Strict constraints:
- NEVER publishes events
- NEVER triggers recovery actions
- NEVER restarts containers
- ONLY reads incident data and writes to grok_summary / grok_recommendations
"""
from __future__ import annotations

import logging

from agent.ai.grok_client import GrokClient
from agent.ai.prompts import root_cause_prompt, summary_prompt, recommendation_prompt
from agent.events.incident import Incident

logger = logging.getLogger(__name__)


class AIAdvisor:
    """
    Enriches Incident objects with AI-generated content from Grok.

    Called by DiagnosisEngine after rule-based diagnosis completes.
    Returns the enriched Incident — never raises.

    The AI Layer is intentionally isolated:
    - It receives an Incident, reads it, writes AI fields, returns it.
    - It has no reference to the EventBus.
    - It has no reference to Docker or any recovery system.
    """

    def __init__(self, grok_client: GrokClient) -> None:
        self._client = grok_client

    def enrich(self, incident: Incident) -> Incident:
        """
        Enrich the incident with AI-generated explanation and recommendations.

        Gracefully degrades: if either Grok call fails, the other is still attempted.
        The incident is always returned, enriched or not.
        """
        logger.info("AIAdvisor: enriching incident '%s'", incident.incident_id)

        # Generate developer-friendly root cause explanation
        incident.grok_summary = self._generate_summary(incident)

        # Generate actionable recommendations
        incident.grok_recommendations = self._generate_recommendations(incident)

        return incident

    def _generate_summary(self, incident: Incident) -> str | None:
        """Generate a concise incident summary via Grok."""
        try:
            prompt = summary_prompt.build_prompt(incident)
            result = self._client.complete(
                prompt=prompt,
                system_prompt=summary_prompt.SYSTEM_PROMPT,
                max_tokens=300,
                temperature=0.3,
            )
            if result:
                logger.debug("AIAdvisor: generated summary (%d chars)", len(result))
            return result
        except Exception:
            logger.exception("AIAdvisor: failed to generate summary")
            return None

    def _generate_recommendations(self, incident: Incident) -> list[str] | None:
        """Generate actionable prevention recommendations via Grok."""
        try:
            prompt = recommendation_prompt.build_prompt(incident)
            result = self._client.complete(
                prompt=prompt,
                system_prompt=recommendation_prompt.SYSTEM_PROMPT,
                max_tokens=400,
                temperature=0.4,
            )
            if result:
                # Parse bullet points into a list
                lines = [
                    line.lstrip("•-* ").strip()
                    for line in result.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                recommendations = [l for l in lines if len(l) > 10]
                logger.debug(
                    "AIAdvisor: generated %d recommendations", len(recommendations)
                )
                return recommendations or None
            return None
        except Exception:
            logger.exception("AIAdvisor: failed to generate recommendations")
            return None
