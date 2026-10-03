from datetime import datetime
from typing import Literal

from pydantic import BaseModel

IncidentStatus = Literal[
    "detected", "diagnosing", "fix_proposed", "validating",
    "validated", "rejected", "pr_opened",
]
SourceType = Literal["github_actions", "docker_runtime"]


class IncidentSource(BaseModel):
    type: SourceType
    workflow_run_url: str | None = None
    container: str | None = None
    commit_sha: str | None = None


class StackFrame(BaseModel):
    file: str
    line: int
    function: str
    code: str
    blame: bool = False


class IncidentError(BaseModel):
    exception_type: str
    message: str
    stack_trace: str
    frames: list[StackFrame]


class Diagnosis(BaseModel):
    root_cause: str
    explanation: str
    suspect_file: str | None = None
    suspect_line: int | None = None
    confidence: float | None = None
    context_files: list[str] = []


class Patch(BaseModel):
    summary: str
    diff: str
    files_changed: list[str]


class Validation(BaseModel):
    result: Literal["PASS", "FAIL"]
    tests_run: int
    tests_passed: int
    bug_reproduced_before_patch: bool
    bug_reproduces_after_patch: bool
    duration_seconds: float
    output: str
    rejection_reason: str | None = None
    finished_at: datetime


class PullRequest(BaseModel):
    number: int
    url: str
    branch: str
    state: Literal["open", "merged", "closed"]


class TimelineEntry(BaseModel):
    status: IncidentStatus
    at: datetime
    message: str | None = None


class Incident(BaseModel):
    id: str
    repo: str
    status: IncidentStatus
    source: IncidentSource
    error: IncidentError
    diagnosis: Diagnosis | None = None
    patch: Patch | None = None
    validation: Validation | None = None
    pull_request: PullRequest | None = None
    timeline: list[TimelineEntry]
    created_at: datetime
    updated_at: datetime


class IncidentSummary(BaseModel):
    id: str
    repo: str
    status: IncidentStatus
    exception_type: str
    message: str
    source_type: SourceType
    validation_result: Literal["PASS", "FAIL"] | None = None
    pr_url: str | None = None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    items: list[IncidentSummary]
    total: int
    page: int
    page_size: int
