"""
Phoenix Agent — Retry Health Strategy

Retries the health endpoint N times with a delay between attempts.
Used for transient health endpoint failures before escalating.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests
import requests.exceptions

from agent.events.incident import FailureType, Incident, RecoveryResult
from agent.recovery.strategies.base import RecoveryStrategy

logger = logging.getLogger(__name__)


class RetryHealthStrategy(RecoveryStrategy):
    """
    Recovery strategy: retry the health endpoint multiple times.

    Applicable to: HEALTH_ENDPOINT_FAILURE.
    Does not restart containers — just retries the check.
    If health is restored, recovery is successful.
    """

    name = "RetryHealthStrategy"
    priority = 5  # try this before restarting

    def __init__(
        self,
        health_url: str,
        max_attempts: int = 5,
        delay_seconds: float = 3.0,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._health_url = health_url
        self._max_attempts = max_attempts
        self._delay = delay_seconds
        self._timeout = timeout_seconds

    def can_handle(self, incident: Incident) -> bool:
        return incident.failure_type == FailureType.HEALTH_ENDPOINT_FAILURE

    def execute(self, incident: Incident) -> RecoveryResult:
        logger.info(
            "RetryHealthStrategy: retrying health check at %s (%d attempts)",
            self._health_url, self._max_attempts,
        )
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = requests.get(self._health_url, timeout=self._timeout)
                if response.status_code == 200:
                    logger.info(
                        "RetryHealthStrategy: health restored on attempt %d", attempt
                    )
                    return RecoveryResult(
                        success=True,
                        strategy_name=self.name,
                        message=f"Health endpoint restored on retry attempt {attempt}.",
                        attempt=incident.retry_count + 1,
                    )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                pass

            if attempt < self._max_attempts:
                time.sleep(self._delay)

        return RecoveryResult(
            success=False,
            strategy_name=self.name,
            message=f"Health endpoint still failing after {self._max_attempts} retries.",
            attempt=incident.retry_count + 1,
            error="max_retries_exceeded",
        )
