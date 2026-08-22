"""
Phoenix Agent — Collector Scheduler

Runs each collector plugin on its own independent interval using a
thread pool. Each collector's thread loops independently — no global
sleep or shared lock causes one collector to block another.

Design:
- One daemon thread per registered collector.
- Thread name = collector.name for easy log filtering.
- Failures in one thread do not affect others.
- Snapshots are published to the EventBus for downstream processing.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from agent.events.bus import EventBus
from agent.events.event_types import SNAPSHOT_COLLECTED
from agent.plugins.base import BaseCollector
from agent.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


class CollectorThread(threading.Thread):
    """
    Daemon thread that runs a single collector at a fixed interval.
    """

    def __init__(
        self,
        collector: BaseCollector,
        interval_seconds: int,
        bus: EventBus,
    ) -> None:
        super().__init__(
            name=f"phoenix-collector-{collector.name}",
            daemon=True,
        )
        self._collector = collector
        self._interval = interval_seconds
        self._bus = bus
        self._stop_event = threading.Event()

    def run(self) -> None:
        logger.info(
            "CollectorThread[%s]: starting, interval=%ds",
            self._collector.name, self._interval,
        )
        while not self._stop_event.is_set():
            try:
                snapshot = self._collector.collect()
                self._bus.publish(SNAPSHOT_COLLECTED, snapshot)
                logger.debug(
                    "CollectorThread[%s]: published snapshot (status=%s)",
                    self._collector.name, snapshot.container_status,
                )
            except Exception:
                logger.exception(
                    "CollectorThread[%s]: unexpected error during collect()",
                    self._collector.name,
                )
            self._stop_event.wait(self._interval)

    def stop(self) -> None:
        self._stop_event.set()


class CollectorScheduler:
    """
    Manages the lifecycle of all collector threads.

    Each collector registered in the PluginRegistry is assigned a
    dedicated thread running at its configured interval.
    """

    def __init__(
        self,
        registry: PluginRegistry,
        bus: EventBus,
        intervals: dict[str, int],
    ) -> None:
        """
        Args:
            registry: Registered collector plugins.
            bus: EventBus to publish snapshots onto.
            intervals: Map of collector-name-prefix → interval seconds.
                       e.g. {"docker": 2, "health": 5, "postgres": 10, "redis": 10, "logs": 20}
        """
        self._registry = registry
        self._bus = bus
        self._intervals = intervals
        self._threads: list[CollectorThread] = []

    def _resolve_interval(self, collector: BaseCollector) -> int:
        """
        Determine poll interval for a collector by matching its name prefix.
        Falls back to 15s if no matching prefix is found.
        """
        for prefix, interval in self._intervals.items():
            if collector.name.startswith(prefix):
                return interval
        logger.warning(
            "CollectorScheduler: no interval configured for '%s', using 15s default",
            collector.name,
        )
        return 15

    def start(self) -> None:
        """Start one daemon thread per registered collector."""
        collectors = self._registry.get_all()
        if not collectors:
            logger.warning("CollectorScheduler: no collectors registered — idle")
            return

        for collector in collectors:
            interval = self._resolve_interval(collector)
            thread = CollectorThread(collector, interval, self._bus)
            self._threads.append(thread)
            thread.start()

        logger.info(
            "CollectorScheduler: started %d collector thread(s)", len(self._threads)
        )

    def stop(self) -> None:
        """Signal all collector threads to stop."""
        for thread in self._threads:
            thread.stop()
        for thread in self._threads:
            thread.join(timeout=5)
        logger.info("CollectorScheduler: all threads stopped")

    @property
    def thread_count(self) -> int:
        return len(self._threads)
