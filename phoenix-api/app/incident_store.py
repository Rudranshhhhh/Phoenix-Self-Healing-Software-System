"""
Phoenix API — Incident Store

High-level incident CRUD operations with INC-001 ID generation,
deduplication, and safe concurrent access.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from .database import get_database

logger = logging.getLogger(__name__)


class IncidentStore:
    """High-level incident storage with atomic operations."""

    @staticmethod
    def generate_incident_id() -> str:
        """
        Generate the next incident ID (INC-001, INC-002, ...).
        Atomic using MongoDB $inc operator.
        """
        db = get_database()
        result = db.counters.find_one_and_update(
            {"_id": "incident_seq"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        seq = result.get("seq", 1)
        return f"INC-{seq:03d}"

    @staticmethod
    def check_duplicate(
        repository: str,
        commit: str,
        run_id: Optional[str],
    ) -> Optional[str]:
        """
        Check if an incident already exists for the same (repository, commit, run_id).
        Return the existing incident_id if found, None otherwise.
        """
        db = get_database()
        query = {"repository": repository, "commit": commit}
        if run_id:
            query["run_id"] = run_id
        existing = db.incidents.find_one(query)
        if existing:
            return existing.get("incident_id")
        return None

    @staticmethod
    def create_incident(
        incident_id: str,
        source: str,  # "github_ci" or "docker_runtime"
        repository: str,
        commit: str,
        branch: str,
        payload: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create and store a new incident.
        Returns the incident document.
        """
        db = get_database()
        now = datetime.now(timezone.utc)
        incident = {
            "incident_id": incident_id,
            "source": source,
            "repository": repository,
            "commit": commit,
            "branch": branch,
            "run_id": run_id,  # top-level for dedup index
            "status": "detected",
            "payload": payload,
            "created_at": now,
            "updated_at": now,
            # These are filled in as the pipeline progresses
            "evidence": None,
            "diagnosis": None,
            "patch": None,
            "validation_result": None,
            "git_branch": None,
            "git_commit_sha": None,
            "pr_url": None,
            "pr_number": None,
            "error_reason": None,
            "timeline": [
                {
                    "status": "detected",
                    "timestamp": now.isoformat(),
                    "message": f"Incident detected from {source}",
                }
            ],
        }
        try:
            db.incidents.insert_one(incident)
            logger.info("Incident %s created", incident_id)
            return incident
        except DuplicateKeyError as exc:
            logger.error("Failed to create incident %s (duplicate?): %s", incident_id, exc)
            raise

    @staticmethod
    def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
        """Fetch an incident by ID."""
        db = get_database()
        return db.incidents.find_one({"incident_id": incident_id})

    @staticmethod
    def list_incidents(
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Fetch incidents with optional filters.
        Returns (incidents, total_count).
        """
        db = get_database()
        query = {}
        if status:
            query["status"] = status
        if source:
            query["source"] = source
        total = db.incidents.count_documents(query)
        incidents = (
            db.incidents.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return list(incidents), total

    @staticmethod
    def update_incident_status(
        incident_id: str,
        status: str,
        message: str = "",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Update incident status and add timeline entry.
        kwargs are merged into the incident document.
        """
        db = get_database()
        now = datetime.now(timezone.utc)
        timeline_entry = {
            "status": status,
            "timestamp": now.isoformat(),
            "message": message,
        }
        # Build update with separate $set and $push operators
        update_dict = {
            "$set": {
                "status": status,
                "updated_at": now,
            },
            "$push": {"timeline": timeline_entry},
        }
        # Add any extra fields (evidence, diagnosis, patch, validation_result, etc.)
        update_dict["$set"].update(kwargs)
        
        result = db.incidents.find_one_and_update(
            {"incident_id": incident_id},
            update_dict,
            return_document=True,
        )
        if result:
            logger.info("Incident %s updated to status %s", incident_id, status)
        return result

    @staticmethod
    def set_validation_result(
        incident_id: str,
        validation_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Store the validation result (outcome from SandboxPipeline).
        """
        db = get_database()
        return db.incidents.find_one_and_update(
            {"incident_id": incident_id},
            {
                "$set": {
                    "validation_result": validation_result,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=True,
        )

    @staticmethod
    def set_git_info(
        incident_id: str,
        branch: str,
        commit_sha: str,
        pr_url: Optional[str] = None,
        pr_number: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Store Git branch, commit SHA, and PR info after successful push + PR creation.
        """
        db = get_database()
        update = {
            "git_branch": branch,
            "git_commit_sha": commit_sha,
            "updated_at": datetime.now(timezone.utc),
        }
        if pr_url:
            update["pr_url"] = pr_url
        if pr_number:
            update["pr_number"] = pr_number
        return db.incidents.find_one_and_update(
            {"incident_id": incident_id},
            {"$set": update},
            return_document=True,
        )

    @staticmethod
    def set_error(
        incident_id: str,
        status: str,
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Mark an incident as failed with an error reason.
        """
        db = get_database()
        return IncidentStore.update_incident_status(
            incident_id, status, message=reason, error_reason=reason
        )
