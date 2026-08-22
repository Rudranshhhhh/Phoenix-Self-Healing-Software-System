"""
Phoenix Backend — Incident Repository

All MongoDB read/write operations for the incidents collection.
Zero Flask knowledge — purely a data access layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pymongo import DESCENDING

from backend.db import mongo

logger = logging.getLogger(__name__)


def upsert_incident(incident_doc: dict) -> str:
    """
    Insert or update an incident document by incident_id.
    Returns the incident_id.
    """
    incident_id = incident_doc.get("incident_id")
    if not incident_id:
        raise ValueError("incident_doc must contain 'incident_id'")

    incident_doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    incident_doc["updated_at"] = datetime.now(timezone.utc).isoformat()

    mongo.incidents().update_one(
        {"incident_id": incident_id},
        {"$set": incident_doc},
        upsert=True,
    )
    logger.debug("IncidentRepository: upserted incident '%s'", incident_id)
    return incident_id


def get_incident(incident_id: str) -> Optional[dict]:
    """Find an incident by its UUID incident_id."""
    doc = mongo.incidents().find_one({"incident_id": incident_id})
    return _clean(doc)


def list_incidents(
    service: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = 20,
    skip: int = 0,
) -> list[dict]:
    """List incidents with optional filters, newest first."""
    query: dict = {}
    if service:
        query["service"] = service
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    if resolved is not None:
        query["resolved"] = resolved

    cursor = (
        mongo.incidents()
        .find(query)
        .sort("detected_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    return [_clean(doc) for doc in cursor]


def count_incidents(
    service: Optional[str] = None,
    status: Optional[str] = None,
    resolved: Optional[bool] = None,
) -> int:
    query: dict = {}
    if service:
        query["service"] = service
    if status:
        query["status"] = status
    if resolved is not None:
        query["resolved"] = resolved
    return mongo.incidents().count_documents(query)


def get_active_incidents() -> list[dict]:
    """Return all unresolved incidents."""
    return list_incidents(resolved=False, limit=100)


def get_escalated_incidents() -> list[dict]:
    """Return all escalated incidents."""
    return list_incidents(status="ESCALATED", limit=50)


def _clean(doc: Optional[dict]) -> Optional[dict]:
    """Remove MongoDB's internal _id field from a document."""
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc
