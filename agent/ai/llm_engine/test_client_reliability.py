"""
Phoenix LLM Engine — GroqLLMClient reliability tests (STAGE 2)

Deterministic unit tests for the hardened GroqLLMClient. No real API key and
no network. The OpenAI client is replaced with a fake whose
`chat.completions.create` raises/returns scripted outcomes, and `time.sleep`
is stubbed so the tests run instantly.

Run:
    python -m pytest agent/ai/llm_engine/test_client_reliability.py -v
"""
from __future__ import annotations

import types
from typing import Optional

import pytest
import httpx

from agent.ai.llm_engine import client as client_module
from agent.ai.llm_engine.client import GroqLLMClient, _retry_after_seconds

from openai import RateLimitError, APIStatusError, APIConnectionError


# ============================================================================ #
# Fakes                                                                          #
# ============================================================================ #

def _resp(status_code: int, headers: Optional[dict] = None):
    """A minimal fake httpx.Response sufficient for openai exceptions."""
    return types.SimpleNamespace(
        status_code=status_code,
        headers=headers or {},
        text="",
        request=types.SimpleNamespace(method="POST", url="https://api.groq.com"),
    )


def _conn(msg: str = "down") -> APIConnectionError:
    """Construct an APIConnectionError (requires a keyword message + request)."""
    return APIConnectionError(
        message=msg,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )


def _content(text: str):
    """A fake completions.create return value carrying `choices[0].message.content`."""
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))]
    )


class _FakeCompletions:
    """chat.completions fake: `side_effects` are values to return or exceptions to raise."""
    def __init__(self, side_effects):
        self._side_effects = list(side_effects)
        self.calls = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        eff = self._side_effects[self.calls - 1]
        if isinstance(eff, Exception):
            raise eff
        return eff


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, side_effects, recorded_kwargs=None):
        self.chat = _FakeChat(_FakeCompletions(side_effects))
        # constructor kwargs captured for the timeout test
        self.init_kwargs = recorded_kwargs if recorded_kwargs is not None else {}


def _make_client(side_effects, monkeypatch, **kwargs):
    """Build a GroqLLMClient and replace its OpenAI client with a fake."""
    # Stub sleep so retries are instant.
    sleeps = []
    monkeypatch.setattr(client_module.time, "sleep", lambda s: sleeps.append(s))
    client = GroqLLMClient(api_key="test-key", **kwargs)
    client._client = _FakeOpenAI(side_effects)
    return client, sleeps


# ============================================================================ #
# Tests                                                                          #
# ============================================================================ #

class TestCompleteSuccess:
    def test_returns_stripped_content(self, monkeypatch):
        client, sleeps = _make_client([_content("  hello  ")], monkeypatch)
        assert client.complete(user_prompt="q") == "hello"
        assert sleeps == []

    def test_empty_content_returns_none(self, monkeypatch):
        client, sleeps = _make_client([_content(None)], monkeypatch)
        assert client.complete(user_prompt="q") is None
        assert sleeps == []  # no retry for an empty (non-exception) answer


class TestRateLimit:
    def test_retries_then_succeeds(self, monkeypatch):
        client, sleeps = _make_client(
            [RateLimitError("rl", response=_resp(429), body=None), _content("ok")],
            monkeypatch,
        )
        assert client.complete(user_prompt="q") == "ok"
        assert client._client.chat.completions.calls == 2
        assert len(sleeps) == 1  # one backoff before the retry

    def test_respects_retry_after_header(self, monkeypatch):
        client, sleeps = _make_client(
            [RateLimitError("rl", response=_resp(429, {"retry-after": "7"}), body=None),
             _content("ok")],
            monkeypatch,
        )
        assert client.complete(user_prompt="q") == "ok"
        assert sleeps == [7.0]  # uses Retry-After, not exponential backoff

    def test_all_attempts_fail_returns_none(self, monkeypatch):
        # max_retries=2 -> 3 total attempts
        rl = RateLimitError("rl", response=_resp(429), body=None)
        client, sleeps = _make_client([rl, rl, rl], monkeypatch, max_retries=2)
        assert client.complete(user_prompt="q") is None
        assert client._client.chat.completions.calls == 3
        # The client sleeps after every failed attempt (including the last);
        # max_retries=2 -> 3 total attempts -> 3 backoffs. Existing behaviour.
        assert len(sleeps) == 3


class TestStatusErrors:
    def test_auth_error_returns_none_no_retry(self, monkeypatch):
        client, sleeps = _make_client(
            [APIStatusError("bad key", response=_resp(401), body=None)], monkeypatch,
        )
        assert client.complete(user_prompt="q") is None
        assert client._client.chat.completions.calls == 1  # not retried
        assert sleeps == []

    def test_forbidden_error_returns_none_no_retry(self, monkeypatch):
        client, sleeps = _make_client(
            [APIStatusError("forbidden", response=_resp(403), body=None)], monkeypatch,
        )
        assert client.complete(user_prompt="q") is None
        assert client._client.chat.completions.calls == 1
        assert sleeps == []

    def test_server_error_retries_then_succeeds(self, monkeypatch):
        client, sleeps = _make_client(
            [APIStatusError("boom", response=_resp(503), body=None), _content("ok")],
            monkeypatch,
        )
        assert client.complete(user_prompt="q") == "ok"
        assert client._client.chat.completions.calls == 2
        assert len(sleeps) == 1

    def test_server_error_all_attempts_fail_returns_none(self, monkeypatch):
        err = APIStatusError("boom", response=_resp(500), body=None)
        client, sleeps = _make_client([err, err, err], monkeypatch, max_retries=2)
        assert client.complete(user_prompt="q") is None
        assert client._client.chat.completions.calls == 3


class TestConnection:
    def test_connection_error_retries_then_succeeds(self, monkeypatch):
        client, sleeps = _make_client(
            [_conn("down"), _content("ok")], monkeypatch,
        )
        assert client.complete(user_prompt="q") == "ok"
        assert client._client.chat.completions.calls == 2
        assert len(sleeps) == 1


class TestUnexpectedError:
    def test_unexpected_error_returns_none_no_retry(self, monkeypatch):
        client, sleeps = _make_client([RuntimeError("weird")], monkeypatch)
        assert client.complete(user_prompt="q") is None
        assert client._client.chat.completions.calls == 1
        assert sleeps == []


class TestTimeoutConfigured:
    def test_default_timeout_is_finite(self, monkeypatch):
        captured = {}

        class _RecordingOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.chat = _FakeChat(_FakeCompletions([_content("ok")]))

        monkeypatch.setattr(client_module, "OpenAI", _RecordingOpenAI)
        client = GroqLLMClient(api_key="test-key")
        assert client._timeout == 30.0
        assert captured.get("timeout") == 30.0

    def test_custom_timeout_passed_through(self, monkeypatch):
        captured = {}

        class _RecordingOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.chat = _FakeChat(_FakeCompletions([_content("ok")]))

        monkeypatch.setattr(client_module, "OpenAI", _RecordingOpenAI)
        client = GroqLLMClient(api_key="test-key", request_timeout_seconds=7.5)
        assert client._timeout == 7.5
        assert captured.get("timeout") == 7.5


class TestRetryAfterHelper:
    def test_returns_seconds_when_present(self):
        exc = RateLimitError("rl", response=_resp(429, {"retry-after": "5"}), body=None)
        assert _retry_after_seconds(exc) == 5.0

    def test_returns_none_when_absent(self):
        exc = RateLimitError("rl", response=_resp(429), body=None)
        assert _retry_after_seconds(exc) is None

    def test_returns_none_on_unparseable(self):
        exc = RateLimitError("rl", response=_resp(429, {"retry-after": "soon"}), body=None)
        assert _retry_after_seconds(exc) is None

    def test_returns_none_when_no_response(self):
        assert _retry_after_seconds(RuntimeError("no response")) is None
