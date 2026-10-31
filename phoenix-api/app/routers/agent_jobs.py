"""Private polling API for the Docker-capable Phoenix agent."""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from ..config import config
from ..incident_store import IncidentStore
from ..repository_store import RepositoryStore

router = APIRouter(prefix="/api/agent/jobs", tags=["agent-jobs"])


def _authorize(token: Optional[str]) -> None:
    expected = config.PHOENIX_AGENT_TOKEN
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid agent credentials")


def _public_incident(document: dict) -> dict:
    document = dict(document)
    document.pop("_id", None)
    return document


@router.post("/claim")
def claim_job(
    worker_id: str = Query(..., min_length=1, max_length=100),
    x_phoenix_agent_token: Optional[str] = Header(None),
) -> dict:
    _authorize(x_phoenix_agent_token)
    incident = IncidentStore.claim_next_agent_job(
        worker_id=worker_id,
        lease_seconds=int(os.environ.get("PHOENIX_AGENT_LEASE_SECONDS", "300")),
    )
    if not incident:
        return {"job": None}

    connection = RepositoryStore.get_for_repository(incident["repository"])
    if not connection:
        IncidentStore.set_error(
            incident["incident_id"],
            "agent_failed",
            "No connected repository credentials are available",
        )
        return {"job": None}

    job = {
        "incident": _public_incident(incident),
        "repository": {
            "id": connection.get("id"),
            "owner": connection["owner"],
            "name": connection["name"],
            "fullName": connection["full_name"],
            "defaultBranch": connection.get("default_branch", "main"),
        },
        "github_token": RepositoryStore.get_token(connection),
    }
    return {"job": job}


@router.post("/{incident_id}/result")
def report_result(
    incident_id: str,
    worker_id: str = Query(..., min_length=1, max_length=100),
    result: dict = Body(...),
    x_phoenix_agent_token: Optional[str] = Header(None),
) -> dict:
    _authorize(x_phoenix_agent_token)
    status = result.get("status")
    if status not in {"validated", "rejected", "pr_opened", "agent_failed"}:
        raise HTTPException(status_code=422, detail="Invalid agent result status")
    updated = IncidentStore.update_agent_result(
        incident_id=incident_id,
        worker_id=worker_id,
        status=status,
        result=result,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Job is not leased by this worker")
    return {"status": status, "incident_id": incident_id}
