"""
Phoenix Backend — Incidents API Blueprint

Endpoints:
  GET  /api/incidents              list incidents (paginated, filterable)
  GET  /api/incidents/summary      dashboard summary counts
  GET  /api/incidents/<id>         single incident with full timeline
  POST /api/incidents              create/update incident from agent
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.services import incident_service

bp = Blueprint("incidents", __name__, url_prefix="/api/incidents")


@bp.get("/")
def list_incidents():
    """List incidents with optional filters."""
    service = request.args.get("service")
    status = request.args.get("status")
    severity = request.args.get("severity")
    resolved_str = request.args.get("resolved")
    resolved = None
    if resolved_str is not None:
        resolved = resolved_str.lower() == "true"

    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(1, int(request.args.get("page_size", 20))))

    result = incident_service.list_incidents(
        service=service,
        status=status,
        severity=severity,
        resolved=resolved,
        page=page,
        page_size=page_size,
    )
    return jsonify(result), 200


@bp.get("/summary")
def get_summary():
    """Return dashboard aggregate counts."""
    summary = incident_service.get_dashboard_summary()
    return jsonify(summary), 200


@bp.get("/<incident_id>")
def get_incident(incident_id: str):
    """Return a single incident by UUID."""
    incident = incident_service.get_incident(incident_id)
    if not incident:
        return jsonify({"error": "Incident not found"}), 404
    return jsonify(incident), 200


@bp.post("/")
def create_incident():
    """
    Receive an incident document from the Phoenix Agent.
    Upserts by incident_id — idempotent.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    if not data.get("incident_id"):
        return jsonify({"error": "'incident_id' is required"}), 400

    saved = incident_service.create_or_update_incident(data)

    # Emit real-time update via SocketIO (imported lazily to avoid circular)
    from backend.websocket.events import emit_incident_update
    emit_incident_update(saved)

    return jsonify({"incident_id": saved.get("incident_id"), "status": "ok"}), 201
