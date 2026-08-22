"""
Phoenix Backend — Metric Repository

All MongoDB read/write operations for the metrics collection.
Optimised for time-series ingestion and range queries.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from pymongo import DESCENDING, ASCENDING

from backend.db import mongo

logger = logging.getLogger(__name__)


def insert_metric(metric_doc: dict) -> None:
    """Insert a single metric snapshot."""
    metric_doc.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    mongo.metrics().insert_one(metric_doc)


def get_latest_per_service() -> list[dict]:
    """
    Return the most recent metric snapshot for each unique service.
    Uses aggregation pipeline for efficiency.
    """
    pipeline = [
        {"$sort": {"timestamp": DESCENDING}},
        {
            "$group": {
                "_id": "$service",
                "latest": {"$first": "$$ROOT"},
            }
        },
        {"$replaceRoot": {"newRoot": "$latest"}},
    ]
    results = list(mongo.metrics().aggregate(pipeline))
    return [_clean(doc) for doc in results]


def get_metrics_for_service(
    service: str,
    hours: int = 1,
    limit: int = 500,
) -> list[dict]:
    """
    Return time-series metrics for a single service over the past N hours.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    cursor = (
        mongo.metrics()
        .find(
            {
                "service": service,
                "timestamp": {"$gte": since.isoformat()},
            }
        )
        .sort("timestamp", ASCENDING)
        .limit(limit)
    )
    return [_clean(doc) for doc in cursor]


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc
