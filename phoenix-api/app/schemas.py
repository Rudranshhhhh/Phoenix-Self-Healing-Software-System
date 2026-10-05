"""
Phoenix API — Input/Output Schemas

Pydantic models for webhook payloads and API responses.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================ #
# GitHub Actions CI Payload                                                   #
# ============================================================================ #


class CIWebhookPayload(BaseModel):
    """Expected webhook payload from GitHub Actions `report-failure` step."""

    source: str = Field(default="github_ci", description="Must be 'github_ci'")
    repository: str = Field(description="owner/repo format")
    commit: str = Field(description="Full commit SHA")
    branch: str = Field(description="Branch name (usually main or feature branch)")
    run_id: str = Field(description="GitHub run ID")
    run_url: str = Field(description="Link to the GitHub Actions run")
    workflow: str = Field(description="Workflow name")
    job: Optional[str] = Field(default=None, description="Job name")
    stage: Optional[str] = Field(default=None, description="Stage/step that failed (lint, build, test)")
    logs: Optional[str] = Field(default=None, description="Truncated job logs (tail of output)")

    class Config:
        extra = "allow"  # Allow extra fields for forward compatibility


# ============================================================================ #
# Docker Runtime Incident                                                      #
# ============================================================================ #


class DockerIncidentPayload(BaseModel):
    """Docker runtime incident payload (from the agent or Docker monitor)."""

    source: str = Field(default="docker_runtime", description="Must be 'docker_runtime'")
    repository: str = Field(description="owner/repo format")
    commit: str = Field(description="Commit SHA the container was built from")
    branch: str = Field(description="Branch")
    container_name: str = Field(description="Container name or ID")
    error_type: str = Field(description="Exception type (TypeError, RuntimeError, etc.)")
    error_message: str = Field(description="Error message")
    logs: Optional[str] = Field(default=None, description="Recent container logs")
    stack_trace: Optional[str] = Field(default=None, description="Full stack trace")

    class Config:
        extra = "allow"


# ============================================================================ #
# API Response Models                                                          #
# ============================================================================ #


class IncidentResponse(BaseModel):
    """API response for POST /api/incidents."""

    incident_id: str
    status: str
    message: str = ""


class IncidentDetailResponse(BaseModel):
    """Full incident detail for GET /api/incidents/{id}."""

    incident_id: str
    source: str
    repository: str
    commit: str
    branch: str
    status: str
    error_reason: Optional[str]
    git_branch: Optional[str]
    pr_url: Optional[str]
    pr_number: Optional[int]
    created_at: str
    updated_at: str
    timeline: List[Dict[str, Any]]
    # Optional: diagnostic info
    evidence: Optional[Dict[str, Any]] = None
    diagnosis: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None


class IncidentsListResponse(BaseModel):
    """API response for GET /api/incidents."""

    incidents: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
