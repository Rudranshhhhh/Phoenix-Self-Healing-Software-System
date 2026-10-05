"""
Phoenix LLM Engine — Groq LLM Client

Thin wrapper around the Groq OpenAI-compatible API.

Responsibilities:
- Read GROQ_API_KEY from the environment (never hardcoded).
- Configure the OpenAI client to point at the Groq base URL.
- Provide a single `complete()` method that accepts a prompt and returns
  a raw string response.
- Retry on transient failures (rate limits, 5xx errors).
- Degrade gracefully — returns None on unrecoverable failure; never raises.

This client has zero Phoenix domain knowledge. It only knows how to talk
to the Groq API. All prompt building and response parsing happen elsewhere.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from openai import OpenAI, RateLimitError, APIStatusError, APIConnectionError

logger = logging.getLogger(__name__)

# Groq OpenAI-compatible base URL
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Default model — current Groq production chat model (131k context, 32k completion)
# Override via constructor or GROQ_MODEL env var.
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqLLMClient:
    """
    OpenAI-compatible client for the Groq API.

    Reads credentials from the environment at construction time.
    Falls back gracefully if the API is unavailable.

    Usage
    -----
        client = GroqLLMClient()
        response = client.complete(
            user_prompt="Explain this error: ...",
            system_prompt="You are a Python debugger.",
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.2,
        max_retries: int = 2,
        retry_delay_seconds: float = 3.0,
    ) -> None:
        """
        Args:
            api_key:              Groq API key. Defaults to GROQ_API_KEY env var.
            model:                Model name. Defaults to GROQ_MODEL env var or
                                  llama-3.3-70b-versatile.
            max_tokens:           Maximum tokens in the LLM response.
            temperature:          Sampling temperature (lower = more deterministic).
            max_retries:          Number of retry attempts on transient errors.
            retry_delay_seconds:  Base delay between retries (doubles each attempt).
        """
        resolved_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not resolved_key:
            logger.warning(
                "GroqLLMClient: GROQ_API_KEY is not set — all requests will fail. "
                "Set the GROQ_API_KEY environment variable."
            )

        self._model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds

        # Initialise the OpenAI-compatible client pointing at Groq
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=GROQ_BASE_URL,
        )

        logger.info(
            "GroqLLMClient: initialised (model=%s, max_tokens=%d, temperature=%.1f)",
            self._model,
            self._max_tokens,
            self._temperature,
        )

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[str]:
        """
        Send a chat completion request to Groq and return the response text.

        Args:
            user_prompt:   The user-turn message (the evidence / question).
            system_prompt: Optional system-turn message (role / instructions).
            max_tokens:    Override instance-level max_tokens for this call.
            temperature:   Override instance-level temperature for this call.

        Returns:
            The response text as a string, or None if all retries fail.
            Never raises an exception.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        tokens = max_tokens or self._max_tokens
        temp = temperature if temperature is not None else self._temperature

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 2):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=tokens,
                    temperature=temp,
                )
                content = response.choices[0].message.content
                if content:
                    logger.debug(
                        "GroqLLMClient: received %d chars (attempt %d)",
                        len(content),
                        attempt,
                    )
                    return content.strip()
                logger.warning("GroqLLMClient: empty response from Groq (attempt %d)", attempt)
                return None

            except RateLimitError as exc:
                last_error = exc
                wait = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "GroqLLMClient: rate limited on attempt %d — waiting %.1fs",
                    attempt,
                    wait,
                )
                time.sleep(wait)

            except APIStatusError as exc:
                last_error = exc
                if exc.status_code >= 500:
                    wait = self._retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "GroqLLMClient: server error %d on attempt %d — waiting %.1fs",
                        exc.status_code,
                        attempt,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    # 4xx errors are not retryable (bad request, auth failure, etc.)
                    logger.error(
                        "GroqLLMClient: client error %d — %s",
                        exc.status_code,
                        exc.message,
                    )
                    return None

            except APIConnectionError as exc:
                last_error = exc
                wait = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "GroqLLMClient: connection error on attempt %d — waiting %.1fs: %s",
                    attempt,
                    wait,
                    exc,
                )
                time.sleep(wait)

            except Exception as exc:
                last_error = exc
                logger.exception(
                    "GroqLLMClient: unexpected error on attempt %d: %s", attempt, exc
                )
                return None  # Non-retryable

        logger.error(
            "GroqLLMClient: all %d attempts failed. Last error: %s",
            self._max_retries + 1,
            last_error,
        )
        return None
