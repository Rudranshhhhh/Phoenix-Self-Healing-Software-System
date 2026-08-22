"""
Phoenix Agent — Reporter Base Protocol

Defines the interface every reporter must implement.
Both HTTP and WebSocket reporters share this contract.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.events.incident import Incident, ServiceSnapshot


@runtime_checkable
class BaseReporter(Protocol):
    """Interface contract for all Phoenix reporters."""

    def report_incident(self, incident: Incident) -> None:
        """Send a complete incident document to the backend."""
        ...

    def report_metric(self, snapshot: ServiceSnapshot) -> None:
        """Send a metrics snapshot for time-series storage."""
        ...
