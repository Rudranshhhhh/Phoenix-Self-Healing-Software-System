"""
Phoenix API — Incidents Endpoints

REAL implementation (not mocked):
  POST /api/incidents       — receive CI/Docker incident, start pipeline
  GET /api/incidents        — list incidents
  GET /api/incidents/{id}   — full incident detail
"""
import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from ..config import config
from ..incident_store import IncidentStore
from ..orchestrator import PhoenixOrchestrator
from ..schemas import (
    CIWebhookPayload,
    DockerIncidentPayload,
    IncidentResponse,
    IncidentsListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["incidents"])

orchestrator = PhoenixOrchestrator()


def _verify_webhook_secret(token: Optional[str]) -> bool:
    """
    Verify the X-Phoenix-Token header against the configured webhook secret.
    """
    if not config.PHOENIX_WEBHOOK_SECRET:
        logger.warning("No PHOENIX_WEBHOOK_SECRET configured — skipping auth")
        return True
    if not token:
        return False
    return hmac.compare_digest(token, config.PHOENIX_WEBHOOK_SECRET)


def _is_loop_guard(payload: dict) -> bool:
    """
    Check if this is a Phoenix-generated PR (loop guard).
    Return True if it should be IGNORED.
    """
    # GitHub CI check
    if payload.get("source") == "github_ci":
        branch = payload.get("branch", "")
        # Ignore if branch is phoenix/fix/*
        if branch.startswith("phoenix/fix/"):
            return True
    return False


@router.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_incident(
    payload: dict,  # Accept raw dict, we'll parse it
    background_tasks: BackgroundTasks,
    x_phoenix_token: Optional[str] = Header(None),
) -> IncidentResponse:
    """
    POST /api/incidents

    Webhook endpoint for CI failures (GitHub Actions) and Docker runtime incidents.
    Always returns 202 Accepted immediately.
    Processes the incident in a background task.

    Authentication: X-Phoenix-Token header must match PHOENIX_WEBHOOK_SECRET.
    Loop guard: Ignores incidents from phoenix/fix/* branches.
    Deduplication: Returns existing incident_id if (repo, commit, run_id) already exists.
    """

    # 1. Authenticate
    if not _verify_webhook_secret(x_phoenix_token):
        logger.warning("Unauthorized webhook request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Phoenix-Token header",
        )

    # 2. Parse payload (minimal validation)
    source = payload.get("source")
    if source not in ("github_ci", "docker_runtime"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid source: {source}. Must be 'github_ci' or 'docker_runtime'.",
        )

    repository = payload.get("repository")
    commit = payload.get("commit")
    branch = payload.get("branch")
    run_id = payload.get("run_id")  # may be None for docker_runtime

    if not all([repository, commit, branch]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required fields: repository, commit, branch",
        )

    # 3. Loop guard
    if _is_loop_guard(payload):
        logger.info("Loop guard: ignoring incident from phoenix/fix/* branch")
        return IncidentResponse(
            incident_id="",
            status="ignored",
            message="Loop guard: ignoring Phoenix PR",
        )

    # 4. Deduplication
    existing_id = IncidentStore.check_duplicate(repository, commit, run_id)
    if existing_id:
        logger.info(
            "Deduplication: incident %s already exists for (repo=%s, commit=%s, run_id=%s)",
            existing_id,
            repository,
            commit[:7],
            run_id,
        )
        return IncidentResponse(
            incident_id=existing_id,
            status="duplicate",
            message=f"Incident {existing_id} already exists",
        )

    # 5. Generate incident ID
    incident_id = IncidentStore.generate_incident_id()
    logger.info("Created incident %s", incident_id)

    # 6. Store incident
    try:
        IncidentStore.create_incident(
            incident_id=incident_id,
            source=source,
            repository=repository,
            commit=commit,
            branch=branch,
            payload=payload,
            run_id=run_id,
        )
    except Exception as exc:
        logger.error("Failed to create incident: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store incident",
        )

    # 7. Start background pipeline
    background_tasks.add_task(orchestrator.process_incident, incident_id)

    return IncidentResponse(
        incident_id=incident_id,
        status="detected",
        message="Incident received. Pipeline started.",
    )


@router.get("/incidents", response_model=IncidentsListResponse)
async def list_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    source_filter: Optional[str] = Query(None, alias="source"),
) -> IncidentsListResponse:
    """
    GET /api/incidents

    List incidents with optional filters.
    """
    try:
        incidents, total = IncidentStore.list_incidents(
            skip=skip,
            limit=limit,
            status=status_filter,
            source=source_filter,
        )
        # Convert MongoDB ObjectId to string in timeline
        for inc in incidents:
            if inc.get("_id"):
                del inc["_id"]
        return IncidentsListResponse(
            incidents=incidents,
            total=total,
            page=skip // limit,
            page_size=limit,
        )
    except Exception as exc:
        logger.error("Failed to list incidents: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch incidents",
        )


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """
    GET /api/incidents/{incident_id}

    Get full incident detail.
    """
    try:
        incident = IncidentStore.get_incident(incident_id)
        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} not found",
            )
        if incident.get("_id"):
            del incident["_id"]
        return incident
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch incident %s: %s", incident_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch incident",
        )
