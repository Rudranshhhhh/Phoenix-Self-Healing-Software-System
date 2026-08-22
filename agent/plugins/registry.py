"""
Phoenix Agent — Plugin Registry

Central registry of all collector plugins.
Plugins register themselves at startup; the Scheduler and VerificationEngine
look them up by name.

Design: Open/Closed — new plugins are added by registering, not by
modifying any existing engine code.
"""
from __future__ import annotations

import logging
from typing import Iterator

from agent.plugins.base import BaseCollector

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Manages the lifecycle of all collector plugins.

    Plugins are registered at agent startup and accessed by the Scheduler
    and VerificationEngine. Duplicate registrations (same name) are rejected.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, BaseCollector] = {}

    def register(self, collector: BaseCollector) -> None:
        """Register a collector plugin. Raises if name already registered."""
        if collector.name in self._plugins:
            raise ValueError(
                f"Plugin '{collector.name}' is already registered. "
                "Use a unique name per collector instance."
            )
        self._plugins[collector.name] = collector
        logger.info("PluginRegistry: registered collector '%s' (service=%s)",
                    collector.name, collector.service)

    def unregister(self, name: str) -> None:
        """Remove a collector by name."""
        removed = self._plugins.pop(name, None)
        if removed is None:
            logger.warning("PluginRegistry: tried to unregister unknown plugin '%s'", name)

    def get(self, name: str) -> BaseCollector:
        """Retrieve a registered collector by name. Raises KeyError if not found."""
        try:
            return self._plugins[name]
        except KeyError:
            raise KeyError(f"No collector registered with name '{name}'")

    def get_all(self) -> list[BaseCollector]:
        """Return all registered collectors."""
        return list(self._plugins.values())

    def __iter__(self) -> Iterator[BaseCollector]:
        return iter(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def summary(self) -> list[dict]:
        """Return a human-readable summary of registered plugins."""
        return [
            {"name": p.name, "service": p.service, "type": type(p).__name__}
            for p in self._plugins.values()
        ]
