"""
Phoenix Backend — Incident Service

Business logic for incident management.
Orchestrates the incident_repository.
Single Responsibility: incident lifecycle rules live here.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.repositories import incident_repository as repo

logger = logging.getLogger(__name__)


def create_or_update_incident(incident_doc: dict) -> dict:
    """
    Upsert an incident from the agent.
    Returns the saved incident document.
    """
    incident_id = repo.upsert_incident(incident_doc)
    saved = repo.get_incident(incident_id)
    logger.info(
        "IncidentService: upserted incident '%s' (status=%s)",
        incident_id, incident_doc.get("status"),
    )
    return saved or incident_doc


def get_incident(incident_id: str) -> Optional[dict]:
    return repo.get_incident(incident_id)


def list_incidents(
    service: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return a paginated list of incidents with metadata."""
    skip = (page - 1) * page_size
    items = repo.list_incidents(
        service=service,
        status=status,
        severity=severity,
        resolved=resolved,
        limit=page_size,
        skip=skip,
    )
    total = repo.count_incidents(service=service, status=status, resolved=resolved)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def get_dashboard_summary() -> dict:
    """Return aggregate counts for the overview dashboard."""
    total = repo.count_incidents()
    active = repo.count_incidents(resolved=False)
    resolved = repo.count_incidents(resolved=True)
    escalated = len(repo.get_escalated_incidents())
    return {
        "total_incidents": total,
        "active_incidents": active,
        "resolved_incidents": resolved,
        "escalated_incidents": escalated,
    }
