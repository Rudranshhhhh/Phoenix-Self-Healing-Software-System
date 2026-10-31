"""Persistent connected-repository records and encrypted OAuth credentials."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet

from .config import config
from .database import get_database


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(config.GITHUB_TOKEN_ENCRYPTION_KEY.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


class RepositoryStore:
    """Mongo-backed repository connections scoped to a GitHub user."""

    @staticmethod
    def upsert(
        github_login: str,
        repository: dict[str, Any],
        oauth_token: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        document = {
            "github_login": github_login,
            "id": repository["id"],
            "owner": repository["owner"],
            "name": repository["name"],
            "full_name": repository["fullName"],
            "default_branch": repository.get("defaultBranch", "main"),
            "github_token_encrypted": encrypt_token(oauth_token),
            "updated_at": now,
        }
        db = get_database()
        db.repository_connections.update_one(
            {"github_login": github_login, "full_name": repository["fullName"]},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return {
            "id": document["id"],
            "owner": document["owner"],
            "name": document["name"],
            "fullName": document["full_name"],
            "defaultBranch": document["default_branch"],
        }

    @staticmethod
    def get_for_repository(full_name: str) -> Optional[dict[str, Any]]:
        return get_database().repository_connections.find_one({"full_name": full_name})

    @staticmethod
    def get_for_user(github_login: str) -> Optional[dict[str, Any]]:
        document = get_database().repository_connections.find_one(
            {"github_login": github_login},
            {"_id": 0, "github_token_encrypted": 0},
            sort=[("updated_at", -1)],
        )
        if not document:
            return None
        return {
            "id": document["id"],
            "owner": document["owner"],
            "name": document["name"],
            "fullName": document["full_name"],
            "defaultBranch": document.get("default_branch", "main"),
        }

    @staticmethod
    def get_token(connection: dict[str, Any]) -> str:
        return decrypt_token(connection["github_token_encrypted"])
