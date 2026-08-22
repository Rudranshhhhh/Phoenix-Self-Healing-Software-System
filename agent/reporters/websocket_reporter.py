"""
Phoenix Agent — WebSocket Reporter

Emits real-time events to the Flask-SocketIO backend.
Uses the python-socketio client library.

Events emitted:
  - incident_update  → /incidents namespace
  - metric_update    → /metrics namespace
"""
from __future__ import annotations

import logging
from typing import Optional

import socketio

from agent.events.incident import Incident, ServiceSnapshot

logger = logging.getLogger(__name__)


class WebSocketReporter:
    """
    Pushes real-time incident and metric data to the Flask-SocketIO backend.

    Maintains a persistent Socket.IO connection with auto-reconnect.
    Falls back silently if the backend WebSocket is unavailable.
    """

    def __init__(self, backend_url: str) -> None:
        self._backend_url = backend_url.rstrip("/")
        self._sio: Optional[socketio.Client] = None
        self._connected = False

    def connect(self) -> None:
        """Establish WebSocket connection to the backend."""
        try:
            self._sio = socketio.Client(
                reconnection=True,
                reconnection_attempts=5,
                reconnection_delay=2,
                logger=False,
                engineio_logger=False,
            )

            @self._sio.event
            def connect():
                self._connected = True
                logger.info("WebSocketReporter: connected to %s", self._backend_url)

            @self._sio.event
            def disconnect():
                self._connected = False
                logger.warning("WebSocketReporter: disconnected from backend")

            self._sio.connect(self._backend_url, namespaces=["/incidents", "/metrics"])
        except Exception as exc:
            logger.warning("WebSocketReporter: connection failed: %s", exc)
            self._connected = False

    def report_incident(self, incident: Incident) -> None:
        """Emit an incident update to the /incidents namespace."""
        if not self._is_connected():
            return
        try:
            self._sio.emit(
                "incident_update",
                incident.to_dict(),
                namespace="/incidents",
            )
            logger.debug(
                "WebSocketReporter: emitted incident_update for '%s'",
                incident.incident_id,
            )
        except Exception as exc:
            logger.warning("WebSocketReporter: failed to emit incident: %s", exc)

    def report_metric(self, snapshot: ServiceSnapshot) -> None:
        """Emit a metric update to the /metrics namespace."""
        if not self._is_connected():
            return
        try:
            self._sio.emit(
                "metric_update",
                snapshot.to_dict(),
                namespace="/metrics",
            )
            logger.debug(
                "WebSocketReporter: emitted metric_update for '%s'", snapshot.service
            )
        except Exception as exc:
            logger.warning("WebSocketReporter: failed to emit metric: %s", exc)

    def disconnect(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self._sio and self._connected:
            try:
                self._sio.disconnect()
            except Exception:
                pass

    def _is_connected(self) -> bool:
        return self._sio is not None and self._connected
