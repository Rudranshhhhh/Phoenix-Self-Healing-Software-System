"""
Phoenix Agent — Grok AI Prompt: Incident Summary
"""
from __future__ import annotations

from agent.events.incident import Incident

SYSTEM_PROMPT = """You are Phoenix's AI Advisor — an expert SRE.
Write a concise incident summary suitable for a developer dashboard.
Format: 2-3 sentences. Plain English. Include: what failed, likely cause, impact."""


def build_prompt(incident: Incident) -> str:
    timeline_phases = [e.phase.value for e in incident.timeline]
    return f"""Summarise this incident for a developer dashboard.

Service: {incident.service}
Failure: {incident.failure_type.value}
Severity: {incident.severity.value}
Status: {incident.status.value}
Root Cause: {incident.root_cause}
Recovery Strategy: {incident.recovery_strategy or 'none yet'}
Retry Count: {incident.retry_count}
Timeline Phases: {' → '.join(timeline_phases)}

Write a 2-3 sentence plain-English summary of what happened."""
