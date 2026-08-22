"""
Phoenix Agent — Base Collector Protocol

Defines the interface every collector plugin must implement.
Using Protocol (structural typing) rather than ABC allows duck-typed
plugins without forcing inheritance — true Open/Closed compliance.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.events.incident import ServiceSnapshot


@runtime_checkable
class BaseCollector(Protocol):
    """
    Interface contract for all Phoenix collector plugins.

    Every plugin must:
    - Declare a unique `name` (used for logging and registry lookups)
    - Declare the `service` it monitors
    - Implement `collect()` returning a ServiceSnapshot
    - Implement `is_healthy()` for quick health queries
    """

    name: str
    service: str

    def collect(self) -> ServiceSnapshot:
        """
        Collect a point-in-time snapshot of the monitored service.

        Must never raise — exceptions should be caught internally and
        reflected in the snapshot (e.g. container_status="error").
        """
        ...

    def is_healthy(self, snapshot: ServiceSnapshot) -> bool:
        """
        Return True if the snapshot indicates a healthy service.
        Used by the VerificationEngine post-recovery.
        """
        ...
