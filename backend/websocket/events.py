"""
Phoenix Backend — WebSocket Events

Flask-SocketIO event handlers and emitters.

Namespaces:
  /incidents — incident lifecycle events
  /metrics   — live metric stream

The backend is a relay — it does not generate events, only forwards
what the agent sends via the REST endpoints.
"""
from __future__ import annotations

import logging

from flask_socketio import SocketIO, emit, join_room

logger = logging.getLogger(__name__)

# Lazily initialised — set by app factory
_socketio: SocketIO | None = None


def init_socketio(socketio: SocketIO) -> None:
    """Called by the app factory to bind the SocketIO instance."""
    global _socketio
    _socketio = socketio
    _register_handlers(socketio)


def _register_handlers(sio: SocketIO) -> None:
    """Register all Socket.IO event handlers."""

    @sio.on("connect", namespace="/incidents")
    def on_incidents_connect():
        logger.debug("WebSocket: client connected to /incidents")

    @sio.on("disconnect", namespace="/incidents")
    def on_incidents_disconnect():
        logger.debug("WebSocket: client disconnected from /incidents")

    @sio.on("connect", namespace="/metrics")
    def on_metrics_connect():
        logger.debug("WebSocket: client connected to /metrics")

    @sio.on("disconnect", namespace="/metrics")
    def on_metrics_disconnect():
        logger.debug("WebSocket: client disconnected from /metrics")


def emit_incident_update(incident_doc: dict) -> None:
    """Broadcast an incident update to all /incidents subscribers."""
    if _socketio is None:
        return
    try:
        _socketio.emit(
            "incident_update",
            incident_doc,
            namespace="/incidents",
        )
        logger.debug(
            "WebSocket: emitted incident_update for '%s'",
            incident_doc.get("incident_id"),
        )
    except Exception as exc:
        logger.warning("WebSocket: failed to emit incident_update: %s", exc)


def emit_metric_update(metric_doc: dict) -> None:
    """Broadcast a metric update to all /metrics subscribers."""
    if _socketio is None:
        return
    try:
        _socketio.emit(
            "metric_update",
            metric_doc,
            namespace="/metrics",
        )
    except Exception as exc:
        logger.warning("WebSocket: failed to emit metric_update: %s", exc)


def emit_escalation_alert(incident_doc: dict) -> None:
    """Broadcast a critical escalation alert to all /incidents subscribers."""
    if _socketio is None:
        return
    try:
        _socketio.emit(
            "escalation_alert",
            incident_doc,
            namespace="/incidents",
        )
        logger.warning(
            "WebSocket: 🚨 escalation_alert emitted for '%s'",
            incident_doc.get("incident_id"),
        )
    except Exception as exc:
        logger.warning("WebSocket: failed to emit escalation_alert: %s", exc)
