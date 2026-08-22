"""
Phoenix Agent — Detection Rule Base

Abstract base for all detection rules.
Each rule answers two questions:
  1. Does this snapshot match my failure condition? (matches)
  2. What Incident should I create? (create_incident)

Design: Stateless rules — no side effects. Rules are pure functions
wrapped in a class for polymorphic dispatch.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from agent.events.incident import Incident, ServiceSnapshot


class DetectionRule(ABC):
    """
    Base class for all detection rules.

    Rules are stateless. They receive a ServiceSnapshot, evaluate
    whether a failure condition is met, and produce an Incident.
    """

    @abstractmethod
    def matches(self, snapshot: ServiceSnapshot) -> bool:
        """
        Return True if the snapshot meets this rule's failure condition.
        Must be deterministic and free of side effects.
        """
        ...

    @abstractmethod
    def create_incident(self, snapshot: ServiceSnapshot) -> Incident:
        """
        Create an Incident from the given snapshot.
        Called only when matches() returns True.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this rule, used in logging."""
        ...
