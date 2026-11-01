"""Phoenix API: serves ingested pipeline incidents (plus demo fixtures) to the dashboard."""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from app.fixtures import SERVER_STARTED, STATIC_INCIDENTS, live_incident
from app.ingest import IngestEvent, demo_fixtures_enabled, store
from app.models import Incident, IncidentListResponse, IncidentSummary
from app.database import close_database, init_database
from app.routers.github import router as github_router
from app.routers.agent_jobs import router as agent_jobs_router
from app.routers.analysis import router as analysis_router
from app.routers.incidents import create_incident
from app.incident_store import IncidentStore

app = FastAPI(title="Phoenix API", version="0.1.0")

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,   # required so the session cookie is sent/received
)

# Mount the GitHub OAuth + repo-read router
app.include_router(github_router)
app.include_router(agent_jobs_router)
app.include_router(analysis_router)


@app.on_event("startup")
def startup() -> None:
    if not init_database():
        # Keep health and fixture routes available while MongoDB is starting;
        # incident intake will surface a storage error until it is ready.
        import logging

        logging.getLogger(__name__).warning("MongoDB is unavailable; incident persistence is offline")


@app.on_event("shutdown")
def shutdown() -> None:
    close_database()


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str


def all_incidents() -> list[Incident]:
    """Static fixtures plus INC-008 in its current state."""
    elapsed = (datetime.now(timezone.utc) - SERVER_STARTED).total_seconds()
    return [*STATIC_INCIDENTS, live_incident(elapsed)]


def current_incidents() -> list[Incident]:
    """Ingested incidents, plus the demo fixtures when DEMO_FIXTURES is on (ingested wins on id clash)."""
    real = store.list()
    if not demo_fixtures_enabled():
        return real
    real_ids = {i.id for i in real}
    return [*real, *(i for i in all_incidents() if i.id not in real_ids)]


def summarize(incident: Incident) -> IncidentSummary:
    return IncidentSummary(
        id=incident.id,
        repo=incident.repo,
        status=incident.status,
        exception_type=incident.error.exception_type,
        message=incident.error.message,
        source_type=incident.source.type,
        validation_result=incident.validation.result if incident.validation else None,
        pr_url=incident.pull_request.url if incident.pull_request else None,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health")
def legacy_health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/incidents", response_model=IncidentListResponse)
def list_incidents(
    status: str | None = Query(None, description="Comma-separated statuses, e.g. validated,pr_opened"),
    repo: str | None = Query(None, description="owner/name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    skip: int | None = Query(None, ge=0),
    limit: int | None = Query(None, ge=1, le=100),
    repository: str | None = Query(None, description="owner/name repository filter"),
) -> IncidentListResponse:
    incidents = current_incidents()
    if status:
        wanted = {s.strip() for s in status.split(",") if s.strip()}
        incidents = [i for i in incidents if i.status in wanted]
    if repo:
        incidents = [i for i in incidents if i.repo == repo]
    if repository:
        incidents = [i for i in incidents if i.repo == repository]
    incidents.sort(key=lambda i: i.updated_at, reverse=True)

    mongo_incidents: list[dict] = []
    try:
        mongo_incidents, mongo_total = IncidentStore.list_incidents(
            skip=skip if skip is not None else (page - 1) * page_size,
            limit=limit if limit is not None else page_size,
            status=status if status and "," not in status else None,
            source=None,
            repository=repository,
        )
        for incident in mongo_incidents:
            incident.pop("_id", None)
    except RuntimeError:
        mongo_total = 0

    start = (page - 1) * page_size
    return IncidentListResponse(
        items=[summarize(i) for i in incidents[start : start + page_size]],
        total=mongo_total if mongo_incidents else len(incidents),
        page=(skip // (limit or page_size)) if skip is not None else page,
        page_size=limit or page_size,
        incidents=mongo_incidents,
    )


@app.get("/api/incidents/{incident_id}", responses={404: {"model": ErrorResponse}})
def get_incident(incident_id: str) -> Incident | dict:
    try:
        mongo_incident = IncidentStore.get_incident(incident_id)
    except RuntimeError:
        mongo_incident = None
    if mongo_incident:
        mongo_incident.pop("_id", None)
        return mongo_incident
    for incident in current_incidents():
        if incident.id == incident_id:
            return incident
    raise HTTPException(status_code=404, detail="Incident not found")


@app.post("/api/ingest/events", response_model=Incident)
def ingest_event(event: IngestEvent, x_phoenix_token: Optional[str] = Header(default=None)) -> Incident:
    expected = os.environ.get("PHOENIX_INGEST_TOKEN")
    if expected and x_phoenix_token != expected:
        raise HTTPException(status_code=401, detail="Invalid ingest token")
    try:
        return store.apply(event)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


app.add_api_route(
    "/api/incidents",
    create_incident,
    methods=["POST"],
    status_code=202,
)
