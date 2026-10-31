"""Mongo-backed repository analysis jobs and results."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

from .database import get_database


class AnalysisStore:
    @staticmethod
    def enqueue(repository: str, github_login: str) -> dict[str, Any]:
        db = get_database()
        now = datetime.now(timezone.utc)
        document = {
            "repository": repository,
            "github_login": github_login,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
        }
        db.repository_analysis.update_one(
            {"repository": repository, "github_login": github_login},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return document

    @staticmethod
    def get(repository: str, github_login: str) -> Optional[dict[str, Any]]:
        return get_database().repository_analysis.find_one(
            {"repository": repository, "github_login": github_login},
            {"_id": 0},
        )

    @staticmethod
    def claim(worker_id: str, lease_seconds: int) -> Optional[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return get_database().repository_analysis.find_one_and_update(
            {
                "status": {"$in": ["queued", "processing"]},
                "$or": [{"status": "queued"}, {"lease_expires_at": {"$lt": now}}],
            },
            {
                "$set": {
                    "status": "processing",
                    "worker_id": worker_id,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )

    @staticmethod
    def report(repository: str, worker_id: str, result: dict[str, Any]) -> Optional[dict[str, Any]]:
        status = result.get("status", "failed")
        return get_database().repository_analysis.find_one_and_update(
            {"repository": repository, "status": "processing", "worker_id": worker_id},
            {
                "$set": {
                    "status": status,
                    "result": result,
                    "error": result.get("error"),
                    "updated_at": datetime.now(timezone.utc),
                    "lease_expires_at": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
