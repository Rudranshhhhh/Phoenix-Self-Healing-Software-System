"""
Phoenix Agent — Internal Event Bus

Thread-safe, in-process publish/subscribe event bus.

Design decisions:
- Uses threading.Lock for thread-safe handler registration.
- Handlers are called synchronously in the publisher's thread.
  For long-running handlers (e.g. Grok API calls), use a thread pool
  or background task queue at the handler level.
- Exceptions in one handler do NOT prevent other handlers from running.
- Designed for single-process use. Not for distributed messaging.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[Any], None]


class EventBus:
    """
    Simple synchronous publish/subscribe event bus.

    Usage:
        bus = EventBus()
        bus.subscribe("IncidentDetected", my_handler)
        bus.publish("IncidentDetected", incident)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for the given event type."""
        with self._lock:
            self._handlers[event_type].append(handler)
        logger.debug("EventBus: subscribed %s → %s", event_type, handler.__qualname__)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                logger.warning(
                    "EventBus: tried to unsubscribe unknown handler %s from %s",
                    handler.__qualname__,
                    event_type,
                )

    def publish(self, event_type: str, payload: Any = None) -> None:
        """
        Publish an event to all registered handlers.

        Handlers are called in registration order.
        A failing handler logs the exception and does not block others.
        """
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        if not handlers:
            logger.debug("EventBus: no handlers for event '%s'", event_type)
            return

        logger.debug(
            "EventBus: publishing '%s' to %d handler(s)", event_type, len(handlers)
        )
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception(
                    "EventBus: handler %s raised an exception for event '%s'",
                    handler.__qualname__,
                    event_type,
                )

    def subscribers(self, event_type: str) -> list[str]:
        """Return the qualified names of all handlers for an event type."""
        with self._lock:
            return [h.__qualname__ for h in self._handlers.get(event_type, [])]
