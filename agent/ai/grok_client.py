"""
Phoenix Agent — Grok API Client

Low-level HTTP client for the xAI Grok API.
Handles: authentication, retries, rate limiting, timeout.

Design:
- Single responsibility: HTTP communication only.
- No Phoenix domain knowledge — takes prompt string, returns string.
- Retries on 429 (rate limit) and 5xx errors with exponential backoff.
- Falls back gracefully on timeout or failure.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests
import requests.exceptions

logger = logging.getLogger(__name__)

GROK_API_BASE = "https://api.x.ai/v1"


class GrokClient:
    """
    HTTP client for the xAI Grok API (/v1/chat/completions).

    Usage:
        client = GrokClient(api_key="your_api_key", model="grok-3-mini")
        response = client.complete("Explain this error: ...")
    """

    def __init__(
        self,
        api_key: str,
        model: str = "grok-3-mini",
        timeout_seconds: int = 15,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """
        Send a prompt to Grok and return the text response.

        Returns None if the request fails after all retries.
        Never raises — all exceptions are caught and logged.
        """
        payload = {
            "model": self._model,
            "messages": [],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})

        for attempt in range(1, self._max_retries + 2):
            try:
                response = self._session.post(
                    f"{GROK_API_BASE}/chat/completions",
                    json=payload,
                    timeout=self._timeout,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning("GrokClient: rate limited — waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    logger.warning(
                        "GrokClient: server error %d on attempt %d",
                        response.status_code, attempt,
                    )
                    time.sleep(2 ** attempt)
                    continue

                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.debug("GrokClient: received %d chars from Grok", len(content))
                return content.strip()

            except requests.exceptions.Timeout:
                logger.warning(
                    "GrokClient: timeout after %ds on attempt %d",
                    self._timeout, attempt,
                )
            except requests.exceptions.ConnectionError as exc:
                logger.warning("GrokClient: connection error on attempt %d: %s", attempt, exc)
            except Exception as exc:
                logger.exception("GrokClient: unexpected error on attempt %d: %s", attempt, exc)

            if attempt <= self._max_retries:
                time.sleep(2 ** attempt)

        logger.error("GrokClient: all %d attempts failed", self._max_retries + 1)
        return None
