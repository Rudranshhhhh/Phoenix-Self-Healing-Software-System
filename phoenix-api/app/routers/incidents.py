"""
Phoenix API — Incidents Router

POST /api/incidents  — receive a CI or Docker failure, store it, queue for the agent
GET  /api/incidents  — list (also served by main.py for fixture blending)
GET  /api/incidents/{id}
"""
import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from ..config import config
from ..incident_store import IncidentStore
from ..repository_store import RepositoryStore
from ..schemas import IncidentResponse, IncidentsListResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["incidents"])


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _verify_token(token: Optional[str]) -> bool:
    secret = config.PHOENIX_WEBHOOK_SECRET
    if not secret:
        logger.warning("PHOENIX_WEBHOOK_SECRET not configured — accepting all requests")
        return True
    if not token:
        return False
    return hmac.compare_digest(token, secret)


# ---------------------------------------------------------------------------
# POST /api/incidents
# ---------------------------------------------------------------------------

@router.post("/api/incidents", response_model=IncidentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_incident(
    payload: dict,
    background_tasks: BackgroundTasks,
    x_phoenix_token: Optional[str] = Header(default=None),
) -> IncidentResponse:
    """
    Webhook entry-point: GitHub Actions or Docker runtime POSTs a failure here.
    Returns 202 immediately; queues work for the local agent worker.
    """

    # ── 1. Auth ──────────────────────────────────────────────────────────────
    if not _verify_token(x_phoenix_token):
        logger.warning(
            "POST /api/incidents: 401 — token mismatch. "
            "Ensure GitHub Actions secret PHOENIX_WEBHOOK_SECRET matches Render env var."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Phoenix-Token. "
                   "Set PHOENIX_WEBHOOK_SECRET in GitHub Actions secrets and Render env vars.",
        )

    # ── 2. Validate payload ───────────────────────────────────────────────────
    source = payload.get("source")
    if source not in ("github_ci", "docker_runtime"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid source '{source}'. Must be 'github_ci' or 'docker_runtime'.",
        )

    repository = payload.get("repository", "").strip()
    commit     = payload.get("commit", "").strip()
    branch     = payload.get("branch", "").strip()
    run_id     = payload.get("run_id")

    if not repository or not commit or not branch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required fields: repository, commit, branch",
        )

    logger.info(
        "POST /api/incidents: source=%s repo=%s branch=%s commit=%.7s run_id=%s",
        source, repository, branch, commit, run_id,
    )

    # ── 3. Loop guard — ignore Phoenix's own fix branches ────────────────────
    if branch.startswith("phoenix/fix/"):
        logger.info("Loop guard: ignoring push on phoenix/fix/* branch")
        return IncidentResponse(incident_id="", status="ignored", message="Loop guard: phoenix/fix/* branch")

    # ── 4. Deduplication ──────────────────────────────────────────────────────
    existing_id = IncidentStore.check_duplicate(repository, commit, run_id)
    if existing_id:
        logger.info("Dedup: incident %s already exists for this (repo, commit, run_id)", existing_id)
        return IncidentResponse(
            incident_id=existing_id,
            status="duplicate",
            message=f"Already tracking {existing_id}",
        )

    # ── 5. Create incident ────────────────────────────────────────────────────
    incident_id = IncidentStore.generate_incident_id()
    connection  = RepositoryStore.get_for_repository(repository)

    logger.info(
        "Creating incident %s | connected=%s",
        incident_id,
        connection.get("full_name") if connection else "none",
    )

    try:
        IncidentStore.create_incident(
            incident_id=incident_id,
            source=source,
            repository=repository,
            commit=commit,
            branch=branch,
            payload=payload,
            run_id=str(run_id) if run_id else None,
            connected_github_login=connection.get("github_login") if connection else None,
        )
    except Exception as exc:
        logger.exception("Failed to persist incident %s: %s", incident_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store incident — check MongoDB connection.",
        )

    # ── 6. Queue for agent ────────────────────────────────────────────────────
    if connection:
        IncidentStore.update_incident_status(
            incident_id,
            "queued_for_agent",
            message="Queued for the connected Phoenix agent",
        )
        logger.info("Incident %s queued_for_agent (worker will poll and claim it)", incident_id)
    else:
        logger.warning(
            "Incident %s has no connected repository — not queued for agent. "
            "User must connect the repo at /connect first.",
            incident_id,
        )

    return IncidentResponse(
        incident_id=incident_id,
        status="detected",
        message="Incident received. Pipeline started.",
    )


# ---------------------------------------------------------------------------
# GET /api/incidents  (thin pass-through — main.py also serves this with fixtures)
# ---------------------------------------------------------------------------

@router.get("/api/incidents/list", response_model=IncidentsListResponse)
async def list_incidents_direct(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    repository: Optional[str] = Query(None),
) -> IncidentsListResponse:
    """Raw MongoDB incident list (no fixture blending)."""
    try:
        incidents, total = IncidentStore.list_incidents(
            skip=skip, limit=limit, status=status_filter, repository=repository
        )
        for inc in incidents:
            inc.pop("_id", None)
        return IncidentsListResponse(incidents=incidents, total=total, page=skip // max(limit, 1), page_size=limit)
    except Exception as exc:
        logger.exception("list_incidents failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch incidents")
