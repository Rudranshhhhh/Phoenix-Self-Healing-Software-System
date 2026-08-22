"""
Phoenix Agent — Grok AI Prompt: Root Cause Explanation
"""
from __future__ import annotations

from agent.events.incident import Incident

SYSTEM_PROMPT = """You are Phoenix's AI Advisor — an expert SRE and DevOps engineer.
Your job is to explain software incidents in clear, developer-friendly language.
Be concise. Use plain language. Avoid jargon. Maximum 3 sentences.
Focus on the most likely root cause based on the symptoms."""


def build_prompt(incident: Incident) -> str:
    snap = incident.metrics_snapshot
    return f"""An incident occurred in a Dockerized application. Explain the likely root cause.

Service: {incident.service}
Container: {incident.container_name}
Failure Type: {incident.failure_type.value}
Severity: {incident.severity.value}
Container Status: {snap.container_status}
CPU Usage: {snap.cpu_percent:.1f}%
Memory Usage: {snap.memory_percent:.1f}% ({snap.memory_mb:.0f} MB)
Restart Count: {snap.restart_count}
Health Status: {snap.health_status or 'unknown'}
DB Reachable: {snap.db_reachable}
Redis Reachable: {snap.redis_reachable}
Log Errors (last 3): {snap.log_errors[:3] if snap.log_errors else 'none'}

Rule-based diagnosis: {incident.root_cause}
Confidence: {incident.confidence_score * 100:.0f}%

Provide a concise, developer-friendly explanation of what likely went wrong and why."""
