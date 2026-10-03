"""Phoenix API stub: serves fake incidents so the dashboard can be built against real HTTP."""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.fixtures import SERVER_STARTED, STATIC_INCIDENTS, live_incident
from app.models import Incident, IncidentListResponse, IncidentSummary

app = FastAPI(title="Phoenix API (stub)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
    incidents = all_incidents()
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
    for incident in all_incidents():
        if incident.id == incident_id:
            return incident
    raise HTTPException(status_code=404, detail="Incident not found")
