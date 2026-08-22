"""
Phoenix Agent — Wait and Retry Strategy

A passive recovery strategy: wait N seconds and re-evaluate.
Useful for transient resource spikes that may self-resolve.
"""
from __future__ import annotations

import logging
import time

from agent.events.incident import FailureType, Incident, RecoveryResult
from agent.recovery.strategies.base import RecoveryStrategy

logger = logging.getLogger(__name__)

_HANDLED_TYPES = {FailureType.HIGH_CPU, FailureType.HIGH_MEMORY}


class WaitAndRetryStrategy(RecoveryStrategy):
    """
    Passive recovery: wait and let the issue self-resolve.

    Used for HIGH_CPU and HIGH_MEMORY as a first attempt before
    restarting the container (which is more disruptive).
    """

    name = "WaitAndRetryStrategy"
    priority = 8  # try before RestartContainer for resource spikes

    def __init__(self, wait_seconds: int = 30) -> None:
        self._wait = wait_seconds

    def can_handle(self, incident: Incident) -> bool:
        return incident.failure_type in _HANDLED_TYPES and incident.retry_count == 0

    def execute(self, incident: Incident) -> RecoveryResult:
        logger.info(
            "WaitAndRetryStrategy: waiting %ds for '%s' to self-recover",
            self._wait, incident.service,
        )
        time.sleep(self._wait)
        return RecoveryResult(
            success=False,  # success is determined by VerificationEngine post-wait
            strategy_name=self.name,
            message=f"Waited {self._wait}s — verification will determine if resolved.",
            attempt=incident.retry_count + 1,
        )
