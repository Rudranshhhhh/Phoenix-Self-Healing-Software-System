"""
Phoenix Agent — Recovery Strategy Base

Abstract base class for all recovery strategies.
Every strategy answers two questions:
  1. Can I handle this incident? (can_handle)
  2. What is the result of my recovery attempt? (execute)
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from agent.events.incident import Incident, RecoveryResult


class RecoveryStrategy(ABC):
    """
    Abstract base for all recovery strategies.

    Strategies are evaluated in priority order (lower = higher priority).
    The first strategy whose can_handle() returns True is executed.
    """

    @abstractmethod
    def can_handle(self, incident: Incident) -> bool:
        """Return True if this strategy applies to the given incident."""
        ...

    @abstractmethod
    def execute(self, incident: Incident) -> RecoveryResult:
        """
        Execute the recovery action.

        Must never raise — exceptions should be caught and returned
        as a RecoveryResult(success=False, error=str(exc)).
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy identifier, used in logging and incident records."""
        ...

    @property
    def priority(self) -> int:
        """
        Lower value = higher priority.
        Override in subclasses to change execution order.
        Default: 100 (low priority fallback).
        """
        return 100
