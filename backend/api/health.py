"""Phoenix Backend — Health & Containers API Blueprints"""
from __future__ import annotations

from flask import Blueprint, jsonify

from backend.services import metric_service

# Health Blueprint
health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
def health():
    """Liveness probe — returns 200 if the backend is running."""
    return jsonify({"status": "ok", "service": "phoenix-backend"}), 200


# Containers Blueprint
containers_bp = Blueprint("containers", __name__, url_prefix="/api/containers")


@containers_bp.get("/")
def get_containers():
    """
    Return the current state of all monitored containers.
    Derived from the latest metric snapshot per service.
    """
    latest = metric_service.get_all_latest()
    containers = [
        {
            "service": m.get("service"),
            "container_name": m.get("container_name"),
            "container_status": m.get("container_status", "unknown"),
            "cpu_percent": m.get("cpu_percent", 0),
            "memory_percent": m.get("memory_percent", 0),
            "memory_mb": m.get("memory_mb", 0),
            "restart_count": m.get("restart_count", 0),
            "health_status": m.get("health_status"),
            "last_seen": m.get("collected_at") or m.get("timestamp"),
        }
        for m in latest
    ]
    return jsonify(containers), 200
