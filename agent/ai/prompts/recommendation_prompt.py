"""
Phoenix Agent — Grok AI Prompt: Recovery Recommendations
"""
from __future__ import annotations

from agent.events.incident import Incident

SYSTEM_PROMPT = """You are Phoenix's AI Advisor — an expert SRE and DevOps engineer.
Provide actionable recommendations for a developer to prevent this incident from recurring.
Format: 3-5 bullet points. Be specific and practical. No generic advice."""


def build_prompt(incident: Incident) -> str:
    return f"""Provide actionable recommendations to prevent this incident from recurring.

Service: {incident.service}
Failure Type: {incident.failure_type.value}
Root Cause: {incident.root_cause}
CPU at detection: {incident.metrics_snapshot.cpu_percent:.1f}%
Memory at detection: {incident.metrics_snapshot.memory_percent:.1f}%
Restart Count: {incident.metrics_snapshot.restart_count}
Log Errors: {incident.metrics_snapshot.log_errors[:3] if incident.metrics_snapshot.log_errors else 'none'}
Recovery Strategy Used: {incident.recovery_strategy or 'none'}
Retry Count: {incident.retry_count}

Provide 3-5 specific, actionable bullet-point recommendations to prevent this failure.
Each recommendation must start with an action verb (e.g. Add, Configure, Implement, Set, Monitor)."""
