"""
Phoenix Backend — Metrics API Blueprint

Endpoints:
  GET  /api/metrics                latest snapshot per service
  GET  /api/metrics/<service>      time-series data for charting
  POST /api/metrics                ingest from agent
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.services import metric_service

bp = Blueprint("metrics", __name__, url_prefix="/api/metrics")


@bp.get("/")
def get_latest():
    """Return the most recent metric snapshot per service."""
    data = metric_service.get_all_latest()
    return jsonify(data), 200


@bp.get("/<service>")
def get_service_metrics(service: str):
    """Return time-series metrics for a specific service."""
    hours = int(request.args.get("hours", 1))
    data = metric_service.get_service_time_series(service=service, hours=hours)
    return jsonify(data), 200


@bp.post("/")
def ingest_metric():
    """Receive a metrics snapshot from the Phoenix Agent."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    metric_service.ingest_metric(data)

    # Emit real-time metric update via SocketIO
    from backend.websocket.events import emit_metric_update
    emit_metric_update(data)

    return jsonify({"status": "ok"}), 201
