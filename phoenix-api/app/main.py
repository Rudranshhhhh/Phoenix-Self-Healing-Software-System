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

app = FastAPI(title="Phoenix API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/incidents", response_model=IncidentListResponse)
def list_incidents(
    status: str | None = Query(None, description="Comma-separated statuses, e.g. validated,pr_opened"),
    repo: str | None = Query(None, description="owner/name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> IncidentListResponse:
    incidents = current_incidents()
    if status:
        wanted = {s.strip() for s in status.split(",") if s.strip()}
        incidents = [i for i in incidents if i.status in wanted]
    if repo:
        incidents = [i for i in incidents if i.repo == repo]
    incidents.sort(key=lambda i: i.updated_at, reverse=True)

    start = (page - 1) * page_size
    return IncidentListResponse(
        items=[summarize(i) for i in incidents[start : start + page_size]],
        total=len(incidents),
        page=page,
        page_size=page_size,
    )


@app.get(
    "/api/incidents/{incident_id}",
    response_model=Incident,
    responses={404: {"model": ErrorResponse}},
)
def get_incident(incident_id: str) -> Incident:
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
