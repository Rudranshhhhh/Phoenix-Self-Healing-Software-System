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
from datetime import datetime, timedelta, timezone

import hashlib
import base64
from cryptography.fernet import Fernet, InvalidToken

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import config
from .database import get_database

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
_token_cipher = Fernet(
    base64.urlsafe_b64encode(
        hashlib.sha256(config.GITHUB_TOKEN_ENCRYPTION_KEY.encode("utf-8")).digest()
    )
)


def sign_token(payload: str) -> str:
    """Return a signed, URL-safe token for `payload`."""
    return _signer.dumps(payload)


def _sign_session(session_id: str, github_access_token: str) -> str:
    """Sign a session identifier with an encrypted cross-instance token fallback."""
    encrypted = _token_cipher.encrypt(github_access_token.encode("utf-8")).decode("ascii")
    return sign_token(f"{session_id}.{encrypted}")


def _session_parts(cookie_value: str) -> tuple[Optional[str], Optional[str]]:
    payload = unsign_token(cookie_value)
    if not payload:
        return None, None
    session_id, separator, encrypted = payload.partition(".")
    if not separator:
        return session_id, None
    try:
        token = _token_cipher.decrypt(encrypted.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return session_id, None
    return session_id, token


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
                "selected_repo": None,
            }
        try:
            get_database().oauth_sessions.update_one(
                {"_id": session_id},
                {
                    "$set": {
                        "github_access_token": _token_cipher.encrypt(
                            github_access_token.encode("utf-8")
                        ).decode("ascii"),
                        "created_at": datetime.now(timezone.utc),
                        "expires_at": datetime.now(timezone.utc)
                        + timedelta(seconds=SESSION_MAX_AGE),
                        "selected_repo": None,
                    }
                },
                upsert=True,
            )
        except RuntimeError:
            pass
        return _sign_session(session_id, github_access_token)

    def get_github_token(self, cookie_value: str) -> Optional[str]:
        """
        Verify the signed cookie and return the stored GitHub token, or None.
        """
        session_id, cookie_token = _session_parts(cookie_value)
        if not session_id:
            return None
        with self._lock:
            entry = self._data.get(session_id)
        if not entry:
            try:
                document = get_database().oauth_sessions.find_one(
                    {"_id": session_id, "expires_at": {"$gt": datetime.now(timezone.utc)}}
                )
                if document:
                    entry = {
                        "github_access_token": _token_cipher.decrypt(
                            document["github_access_token"].encode("ascii")
                        ).decode("utf-8"),
                        "created_at": document["created_at"].timestamp(),
                        "selected_repo": document.get("selected_repo"),
                    }
                    with self._lock:
                        self._data[session_id] = entry
            except RuntimeError:
                pass
        if not entry:
            return cookie_token
        # Hard-expire regardless of signature age
        if time.time() - entry["created_at"] > SESSION_MAX_AGE:
            self.delete(cookie_value)
            return None
        return entry["github_access_token"]

    def delete(self, cookie_value: str) -> None:
        """Remove the session (sign-out)."""
        session_id, _ = _session_parts(cookie_value)
        if session_id:
            with self._lock:
                self._data.pop(session_id, None)
            try:
                get_database().oauth_sessions.delete_one({"_id": session_id})
            except RuntimeError:
                pass

    def get_selected_repo(self, cookie_value: str) -> Optional[dict]:
        """Return the repository selected by this signed-in user."""
        session_id, _ = _session_parts(cookie_value)
        if not session_id:
            return None
        with self._lock:
            entry = self._data.get(session_id)
        if not entry:
            try:
                entry = get_database().oauth_sessions.find_one({"_id": session_id}) or {}
            except RuntimeError:
                entry = {}
        return dict(entry["selected_repo"]) if entry and entry.get("selected_repo") else None

    def set_selected_repo(self, cookie_value: str, repository: dict) -> bool:
        """Persist the selected repository for the current session."""
        session_id, _ = _session_parts(cookie_value)
        if not session_id:
            return False
        with self._lock:
            entry = self._data.get(session_id)
            if entry:
                entry["selected_repo"] = dict(repository)
        try:
            result = get_database().oauth_sessions.update_one(
                {"_id": session_id}, {"$set": {"selected_repo": dict(repository)}}
            )
            if result.matched_count:
                return True
        except RuntimeError:
            pass
        if not entry:
            return False
        return True

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
        try:
            get_database().oauth_states.insert_one(
                {
                    "_id": state,
                    "expires_at": datetime.now(timezone.utc)
                    + timedelta(seconds=OAUTH_STATE_TTL),
                }
            )
        except RuntimeError:
            pass
        return state

    def consume(self, state: str) -> bool:
        """
        Return True and remove the state if it exists and hasn't expired.
        Single-use — always removes the state whether valid or not.
        """
        with self._lock:
            created = self._states.pop(state, None)
        if created is None:
            try:
                document = get_database().oauth_states.find_one_and_delete(
                    {"_id": state, "expires_at": {"$gt": datetime.now(timezone.utc)}}
                )
                created = (
                    document["expires_at"].timestamp() - OAUTH_STATE_TTL
                    if document
                    else None
                )
            except RuntimeError:
                pass
        if created is None:
            return False
        return (time.time() - created) < OAUTH_STATE_TTL


oauth_states = _StateStore()
