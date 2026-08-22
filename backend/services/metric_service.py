"""
Phoenix Backend — Metric Service

Business logic for metric ingestion and aggregation.
"""
from __future__ import annotations

from backend.repositories import metric_repository as repo


def ingest_metric(metric_doc: dict) -> None:
    """Store a single metrics snapshot from the agent."""
    repo.insert_metric(metric_doc)


def get_all_latest() -> list[dict]:
    """Return the most recent snapshot per service for the overview."""
    return repo.get_latest_per_service()


def get_service_time_series(service: str, hours: int = 1) -> list[dict]:
    """Return time-series metrics for charting."""
    return repo.get_metrics_for_service(service=service, hours=hours)
