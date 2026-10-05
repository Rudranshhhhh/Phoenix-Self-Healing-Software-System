"""
Phoenix API — Session Store

Maps opaque session tokens (sent as cookies) to GitHub OAuth access tokens.
Tokens are kept in process memory only — never written to disk or MongoDB.
On restart all sessions expire, which is the safest default for a dev tool.

The session token itself is a signed, time-limited token produced by
itsdangerous.URLSafeTimedSerializer so it cannot be forged even if someone
intercepts the cookie name.
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COOKIE_NAME = "phoenix_session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours
OAUTH_STATE_TTL = 60 * 10      # 10 minutes — state param lifetime


# ---------------------------------------------------------------------------
# Signer
# ---------------------------------------------------------------------------

_signer = URLSafeTimedSerializer(config.SESSION_SECRET_KEY, salt="phoenix-session")


def sign_token(payload: str) -> str:
    """Return a signed, URL-safe token for `payload`."""
    return _signer.dumps(payload)


def unsign_token(token: str, max_age: int = SESSION_MAX_AGE) -> Optional[str]:
    """Verify and return the payload, or None if invalid / expired."""
    try:
        return _signer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Session store  (session_id → github_access_token)
# ---------------------------------------------------------------------------

class _SessionStore:
    """Thread-safe in-memory store: session_id → {access_token, created_at}."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}

    # ------------------------------------------------------------------ #

    def create(self, github_access_token: str) -> str:
        """
        Persist a new session holding `github_access_token`.
        Returns the *signed* session cookie value.
        """
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            self._data[session_id] = {
                "github_access_token": github_access_token,
                "created_at": time.time(),
            }
        return sign_token(session_id)

    def get_github_token(self, cookie_value: str) -> Optional[str]:
        """
        Verify the signed cookie and return the stored GitHub token, or None.
        """
        session_id = unsign_token(cookie_value)
        if not session_id:
            return None
        with self._lock:
            entry = self._data.get(session_id)
        if not entry:
            return None
        # Hard-expire regardless of signature age
        if time.time() - entry["created_at"] > SESSION_MAX_AGE:
            self.delete(cookie_value)
            return None
        return entry["github_access_token"]

    def delete(self, cookie_value: str) -> None:
        """Remove the session (sign-out)."""
        session_id = unsign_token(cookie_value)
        if session_id:
            with self._lock:
                self._data.pop(session_id, None)

    def purge_expired(self) -> None:
        """Remove stale entries (call periodically if desired)."""
        cutoff = time.time() - SESSION_MAX_AGE
        with self._lock:
            stale = [sid for sid, v in self._data.items() if v["created_at"] < cutoff]
            for sid in stale:
                del self._data[sid]


# Module-level singleton
sessions = _SessionStore()


# ---------------------------------------------------------------------------
# OAuth state store  (state → created_at)
# Used to validate the `state` parameter on the GitHub callback.
# ---------------------------------------------------------------------------

class _StateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, float] = {}

    def issue(self) -> str:
        """Generate and store a cryptographically-random state string."""
        state = secrets.token_urlsafe(32)
        with self._lock:
            self._states[state] = time.time()
        return state

    def consume(self, state: str) -> bool:
        """
        Return True and remove the state if it exists and hasn't expired.
        Single-use — always removes the state whether valid or not.
        """
        with self._lock:
            created = self._states.pop(state, None)
        if created is None:
            return False
        return (time.time() - created) < OAUTH_STATE_TTL


oauth_states = _StateStore()
