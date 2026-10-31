from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Cookie, Header, HTTPException, Query

from ..analysis_store import AnalysisStore
from ..repository_store import RepositoryStore
from ..session_store import COOKIE_NAME, sessions
from .github import _github_get
from .agent_jobs import _authorize

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/github/analysis")
async def get_analysis(
    repository: str = Query(..., min_length=3),
    github_login: str = Query(..., min_length=1),
    phoenix_session: Optional[str] = Cookie(None, alias=COOKIE_NAME),
) -> dict:
    if not phoenix_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = sessions.get_github_token(phoenix_session)
    if not token:
        raise HTTPException(status_code=401, detail="Session expired")
    profile = await _github_get("/user", token)
    if profile.get("login") != github_login:
        raise HTTPException(status_code=403, detail="Repository analysis is not owned by this user")
    analysis = AnalysisStore.get(repository, github_login)
    return analysis or {
        "repository": repository,
        "status": "queued",
        "result": None,
    }


@router.post("/agent/analysis/claim")
def claim_analysis(
    worker_id: str = Query(..., min_length=1, max_length=100),
    x_phoenix_agent_token: Optional[str] = Header(None),
) -> dict:
    _authorize(x_phoenix_agent_token)
    job = AnalysisStore.claim(worker_id, 300)
    if not job:
        return {"job": None}
    connection = RepositoryStore.get_for_repository(job["repository"])
    if not connection:
        result = {
            "repository": job["repository"],
            "worker_id": worker_id,
            "status": "failed",
            "error": "No connected repository credentials are available",
        }
        AnalysisStore.report(job["repository"], worker_id, result)
        return {"job": None}
    return {
        "job": {
            "repository": job["repository"],
            "github_login": job["github_login"],
            "github_token": RepositoryStore.get_token(connection),
            "default_branch": connection.get("default_branch", "main"),
        }
    }


@router.post("/agent/analysis/result")
def report_analysis(
    result: dict = Body(...),
    x_phoenix_agent_token: Optional[str] = Header(None),
) -> dict:
    _authorize(x_phoenix_agent_token)
    if result.get("status") not in {"ready", "failed"}:
        raise HTTPException(status_code=422, detail="Invalid analysis result status")
    updated = AnalysisStore.report(result.get("repository", ""), result.get("worker_id", ""), result)
    if not updated:
        raise HTTPException(status_code=409, detail="Analysis job is not leased by this worker")
    return {"status": result["status"], "repository": result["repository"]}
