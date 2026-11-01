"""
Phoenix API — GitHub OAuth Router

Session tokens are accepted two ways:
  1. HttpOnly cookie  (phoenix_session) — works when frontend and API share an origin
  2. X-Phoenix-Session header           — works when they are on different origins
     (e.g. localhost:3000 frontend talking to https://render.com API)

After /api/github/callback the signed session token is placed BOTH in an
HttpOnly cookie AND appended to the redirect URL as ?phoenix_session=…  The
React OAuthCallback page stores that value in sessionStorage and every
subsequent fetch sends it as the X-Phoenix-Session header.  This survives
cross-origin deployments where SameSite=None cookies are blocked.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Body, Cookie, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..analysis_store import AnalysisStore
from ..config import config
from ..incident_store import IncidentStore
from ..repository_store import RepositoryStore
from ..session_store import COOKIE_NAME, SESSION_MAX_AGE, oauth_states, sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/github", tags=["github"])

# ---------------------------------------------------------------------------
# GitHub URLs / OAuth constants
# ---------------------------------------------------------------------------

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL     = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE      = "https://api.github.com"
OAUTH_SCOPES         = "repo,read:user,admin:repo_hook,workflow"

PHOENIX_WORKFLOW_PATH = ".github/workflows/phoenix-monitor.yml"
PHOENIX_WORKFLOW = """\
name: Phoenix Monitor

on: [push, pull_request, workflow_dispatch]

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        if: hashFiles('requirements.txt', 'pyproject.toml') != ''
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Set up Node
        if: hashFiles('package.json') != ''
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Run checks
        shell: bash
        run: |
          set -e
          if [ -f requirements.txt ]; then
            pip install -r requirements.txt
          fi
          if [ -d tests ]; then
            pip install pytest && pytest -q
          fi
          if [ -f package-lock.json ]; then
            npm ci
          elif [ -f package.json ]; then
            npm install
          fi
          if [ -f package.json ]; then
            npm test --if-present
            npm run build --if-present
          fi
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frontend_callback() -> str:
    return f"{config.FRONTEND_URL}/connect/callback"


def _require_oauth_config() -> None:
    if not config.GITHUB_CLIENT_ID or not config.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth is not configured — set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.",
        )


# FastAPI dependency — resolves GitHub token from cookie OR header.
# All protected endpoints declare: token: str = Depends(_require_token)
def _require_token(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    x_phoenix_session: Optional[str] = Header(default=None, alias="X-Phoenix-Session"),
) -> str:
    raw = x_phoenix_session or phoenix_session
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated — visit /api/github/login.")
    token = sessions.get_github_token(raw)
    if not token:
        raise HTTPException(status_code=401, detail="Session expired or invalid — please sign in again.")
    return token


# Same but also returns the raw session string (needed for set_selected_repo).
def _require_session(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    x_phoenix_session: Optional[str] = Header(default=None, alias="X-Phoenix-Session"),
) -> tuple[str, str]:
    raw = x_phoenix_session or phoenix_session
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated — visit /api/github/login.")
    token = sessions.get_github_token(raw)
    if not token:
        raise HTTPException(status_code=401, detail="Session expired or invalid — please sign in again.")
    return token, raw


async def _github_get(path: str, token: str, **params: Any) -> Any:
    url = f"{GITHUB_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=headers, params=params)
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"GitHub resource not found: {path}")
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub token rejected — please sign in again.")
    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error {response.status_code}: {response.text[:300]}",
        )
    return response.json()


# ---------------------------------------------------------------------------
# Step 1 — Redirect to GitHub
# ---------------------------------------------------------------------------

@router.get("/login")
def github_login() -> RedirectResponse:
    _require_oauth_config()
    state = oauth_states.issue()
    qs = urlencode({
        "client_id":    config.GITHUB_CLIENT_ID,
        "redirect_uri": config.GITHUB_REDIRECT_URI,
        "scope":        OAUTH_SCOPES,
        "state":        state,
        "allow_signup": "true",
    })
    return RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{qs}", status_code=302)


# ---------------------------------------------------------------------------
# Step 2 — GitHub sends the browser back here with ?code=&state=
# ---------------------------------------------------------------------------

@router.get("/callback")
async def github_callback(
    code:  str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    _require_oauth_config()

    if not oauth_states.consume(state):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state — please try signing in again.",
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id":     config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  config.GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )

    if not token_resp.is_success:
        logger.error("GitHub token exchange failed: %s", token_resp.text)
        raise HTTPException(status_code=502, detail="Failed to exchange code for GitHub token.")

    token_data   = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        err = token_data.get("error_description", token_data.get("error", "unknown"))
        raise HTTPException(status_code=502, detail=f"GitHub did not return a token: {err}")

    logger.info("GitHub OAuth: token exchange successful")

    # Store on the server; cookie_value is a signed opaque string — NOT the raw token.
    cookie_value = sessions.create(access_token)

    # Redirect to React with the session token in the URL so the frontend can
    # store it in sessionStorage and send it as a header.  This is necessary
    # when the frontend runs on HTTP localhost and cannot receive a Secure cookie.
    redirect_url = f"{_frontend_callback()}?{urlencode({'phoenix_session': cookie_value})}"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite=config.SESSION_COOKIE_SAMESITE,
        max_age=SESSION_MAX_AGE,
        secure=config.SESSION_COOKIE_SECURE,
        path="/",
    )
    return response


# ---------------------------------------------------------------------------
# /me — who is logged in?
# ---------------------------------------------------------------------------

@router.get("/me")
async def github_me(token: str = Depends(_require_token)) -> JSONResponse:
    data = await _github_get("/user", token)
    return JSONResponse({
        "login":       data.get("login"),
        "name":        data.get("name") or data.get("login"),
        "avatarUrl":   data.get("avatar_url"),
        "company":     data.get("company") or "",
        "email":       data.get("email"),
        "publicRepos": data.get("public_repos", 0),
        "privateRepos":data.get("total_private_repos", 0),
    })


# ---------------------------------------------------------------------------
# Selected repository — get / set
# ---------------------------------------------------------------------------

@router.get("/selection")
async def get_selection(token: str = Depends(_require_token)) -> JSONResponse:
    profile  = await _github_get("/user", token)
    selected = RepositoryStore.get_for_user(profile.get("login"))
    return JSONResponse({"repository": selected})


@router.put("/selection")
async def set_selection(
    repository: dict = Body(...),
    auth: tuple[str, str] = Depends(_require_session),
) -> JSONResponse:
    token, raw_session = auth
    required = ("id", "owner", "name", "fullName", "defaultBranch")
    if any(not repository.get(f) for f in required):
        raise HTTPException(status_code=422, detail=f"Repository body requires: {', '.join(required)}")

    selected = {k: repository[k] for k in ("id", "owner", "name", "fullName", "defaultBranch")}

    # Refresh defaultBranch from GitHub in case it changed.
    remote = await _github_get(f"/repos/{selected['owner']}/{selected['name']}", token)
    selected["defaultBranch"] = remote.get("default_branch", selected["defaultBranch"])

    profile   = await _github_get("/user", token)
    connected = RepositoryStore.upsert(profile.get("login", ""), selected, token)
    sessions.set_selected_repo(raw_session, connected)

    # Best-effort: install webhook + monitoring workflow. Never block repo selection.
    try:
        await _ensure_workflow_webhook(selected, token)
    except Exception as exc:
        logger.warning("Webhook registration skipped: %s", exc)
    try:
        await _ensure_monitoring_workflow(selected, token)
    except Exception as exc:
        logger.warning("Monitoring workflow skipped: %s", exc)

    AnalysisStore.enqueue(selected["fullName"], profile.get("login", ""))
    return JSONResponse({"repository": connected})


# ---------------------------------------------------------------------------
# Webhook helpers (internal, called from set_selection)
# ---------------------------------------------------------------------------

async def _ensure_workflow_webhook(repository: dict[str, Any], token: str) -> None:
    callback = f"{config.PHOENIX_PUBLIC_URL}/api/github/webhook"
    secret   = config.PHOENIX_WEBHOOK_SECRET
    owner, name = repository["owner"], repository["name"]

    existing = await _github_get(f"/repos/{owner}/{name}/hooks", token, per_page=100)
    for hook in existing:
        if (hook.get("config") or {}).get("url") == callback:
            # Hook already exists — patch it to make sure it is active.
            hook_id = hook.get("id")
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.patch(
                    f"{GITHUB_API_BASE}/repos/{owner}/{name}/hooks/{hook_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept":        "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={
                        "active": True,
                        "events": ["workflow_run"],
                        "config": {
                            "url":          callback,
                            "content_type": "json",
                            "secret":       secret,
                            "insecure_ssl": "0",
                        },
                    },
                )
            if r.status_code != 200:
                logger.warning("Could not repair webhook %s: HTTP %s", hook_id, r.status_code)
            return

    # No existing hook — create one.
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{GITHUB_API_BASE}/repos/{owner}/{name}/hooks",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept":        "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "name":   "web",
                "active": True,
                "events": ["workflow_run"],
                "config": {
                    "url":          callback,
                    "content_type": "json",
                    "secret":       secret,
                    "insecure_ssl": "0",
                },
            },
        )
    if r.status_code not in (201, 422):   # 422 = already exists race
        logger.warning("Webhook creation for %s/%s returned HTTP %s", owner, name, r.status_code)


async def _ensure_monitoring_workflow(repository: dict[str, Any], token: str) -> None:
    owner, name   = repository["owner"], repository["name"]
    default_branch = repository["defaultBranch"]
    url = f"{GITHUB_API_BASE}/repos/{owner}/{name}/contents/{PHOENIX_WORKFLOW_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        existing = await client.get(url, headers=headers, params={"ref": default_branch})
        if existing.status_code == 200:
            return   # already present
        if existing.status_code != 404:
            logger.warning("Could not inspect workflow for %s/%s: HTTP %s", owner, name, existing.status_code)
            return

        content = base64.b64encode(PHOENIX_WORKFLOW.encode()).decode()
        r = await client.put(
            url,
            headers=headers,
            json={
                "message": "chore: add Phoenix monitoring workflow",
                "content": content,
                "branch":  default_branch,
            },
        )
    if r.status_code not in (200, 201):
        logger.warning("Could not create monitoring workflow for %s/%s: HTTP %s", owner, name, r.status_code)


# ---------------------------------------------------------------------------
# GitHub Actions webhook receiver
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event:      Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
) -> dict:
    body = await request.body()

    # Verify HMAC signature
    expected_sig = "sha256=" + hmac.new(
        config.PHOENIX_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(expected_sig, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event != "workflow_run":
        return {"status": "ignored"}

    payload = json.loads(body)
    run = payload.get("workflow_run") or {}
    if payload.get("action") != "completed" or run.get("conclusion") in {
        "success", "skipped", "neutral", None
    }:
        return {"status": "ignored"}

    repository = (payload.get("repository") or {}).get("full_name")
    commit     = run.get("head_sha")
    branch     = run.get("head_branch") or ""
    run_id     = run.get("id")

    if not repository or not commit or not branch or not run_id:
        raise HTTPException(status_code=422, detail="Incomplete workflow_run payload")

    # Ignore Phoenix's own fix branches to prevent loops.
    if branch.startswith("phoenix/fix/"):
        return {"status": "ignored"}

    incident_id = IncidentStore.generate_incident_id()
    connection  = RepositoryStore.get_for_repository(repository)

    IncidentStore.create_incident(
        incident_id=incident_id,
        source="github_ci",
        repository=repository,
        commit=commit,
        branch=branch,
        payload={
            "source":     "github_ci",
            "repository": repository,
            "commit":     commit,
            "branch":     branch,
            "run_id":     run_id,
            "run_url":    run.get("html_url"),
            "workflow":   run.get("name") or "GitHub Actions",
            "stage":      "workflow_run",
            "logs":       f"GitHub Actions run failed: {run.get('conclusion')}",
        },
        run_id=str(run_id),
        connected_github_login=connection.get("github_login") if connection else None,
    )
    if connection:
        IncidentStore.update_incident_status(
            incident_id, "queued_for_agent", message="Queued for Phoenix agent"
        )
    return {"status": "queued", "incident_id": incident_id}


# ---------------------------------------------------------------------------
# Repos — list
# ---------------------------------------------------------------------------

@router.get("/repos")
async def list_repos(
    token:    str = Depends(_require_token),
    page:     int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> JSONResponse:
    data = await _github_get(
        "/user/repos", token,
        visibility="all",
        affiliation="owner,collaborator,organization_member",
        sort="pushed", direction="desc",
        per_page=per_page, page=page,
    )
    repos = [{
        "id":            r["id"],
        "owner":         r["owner"]["login"],
        "name":          r["name"],
        "fullName":      r["full_name"],
        "private":       r["private"],
        "language":      r.get("language") or "Unknown",
        "pushedAt":      r.get("pushed_at"),
        "defaultBranch": r.get("default_branch", "main"),
        "description":   r.get("description") or "",
        "htmlUrl":       r.get("html_url"),
        "cloneUrl":      r.get("clone_url"),
        "stargazersCount": r.get("stargazers_count", 0),
    } for r in data]
    return JSONResponse({"repos": repos, "page": page, "per_page": per_page})


# ---------------------------------------------------------------------------
# Repos — single repo
# ---------------------------------------------------------------------------

@router.get("/repos/{owner}/{repo}")
async def get_repo(
    owner: str, repo: str,
    token: str = Depends(_require_token),
) -> JSONResponse:
    data = await _github_get(f"/repos/{owner}/{repo}", token)
    return JSONResponse({
        "id":            data["id"],
        "owner":         data["owner"]["login"],
        "name":          data["name"],
        "fullName":      data["full_name"],
        "private":       data["private"],
        "language":      data.get("language") or "Unknown",
        "pushedAt":      data.get("pushed_at"),
        "defaultBranch": data.get("default_branch", "main"),
        "description":   data.get("description") or "",
        "htmlUrl":       data.get("html_url"),
        "cloneUrl":      data.get("clone_url"),
    })


# ---------------------------------------------------------------------------
# Repos — branches
# ---------------------------------------------------------------------------

@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(
    owner: str, repo: str,
    token:    str = Depends(_require_token),
    per_page: int = Query(100, ge=1, le=100),
) -> JSONResponse:
    data = await _github_get(f"/repos/{owner}/{repo}/branches", token, per_page=per_page)
    return JSONResponse({"branches": [{
        "name":      b["name"],
        "sha":       b["commit"]["sha"],
        "protected": b.get("protected", False),
    } for b in data]})


# ---------------------------------------------------------------------------
# Repos — commits
# ---------------------------------------------------------------------------

@router.get("/repos/{owner}/{repo}/commits")
async def list_commits(
    owner: str, repo: str,
    token:    str = Depends(_require_token),
    branch:   Optional[str] = Query(None),
    per_page: int = Query(20, ge=1, le=100),
    page:     int = Query(1, ge=1),
) -> JSONResponse:
    params: dict[str, Any] = {"per_page": per_page, "page": page}
    if branch:
        params["sha"] = branch
    data = await _github_get(f"/repos/{owner}/{repo}/commits", token, **params)
    return JSONResponse({"commits": [{
        "sha":         c["sha"],
        "shortSha":    c["sha"][:7],
        "message":     c["commit"]["message"].split("\n")[0],
        "author":      c["commit"]["author"]["name"],
        "authorEmail": c["commit"]["author"]["email"],
        "date":        c["commit"]["author"]["date"],
        "htmlUrl":     c.get("html_url"),
    } for c in data]})


# ---------------------------------------------------------------------------
# Repos — file / directory contents
# ---------------------------------------------------------------------------

@router.get("/repos/{owner}/{repo}/contents")
async def get_contents(
    owner: str, repo: str,
    token: str = Depends(_require_token),
    path:  str = Query(""),
    ref:   Optional[str] = Query(None),
) -> JSONResponse:
    api_path = f"/repos/{owner}/{repo}/contents/{path}".rstrip("/")
    params: dict[str, Any] = {}
    if ref:
        params["ref"] = ref
    data = await _github_get(api_path, token, **params)

    if isinstance(data, list):
        return JSONResponse({"type": "directory", "path": path or "/", "entries": [{
            "name":        e["name"],
            "path":        e["path"],
            "type":        e["type"],
            "size":        e.get("size", 0),
            "sha":         e["sha"],
            "htmlUrl":     e.get("html_url"),
            "downloadUrl": e.get("download_url"),
        } for e in data]})

    try:
        decoded: Optional[str] = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    except Exception:
        decoded = None
    return JSONResponse({
        "type":        "file",
        "name":        data["name"],
        "path":        data["path"],
        "size":        data.get("size", 0),
        "sha":         data["sha"],
        "encoding":    data.get("encoding"),
        "content":     decoded,
        "htmlUrl":     data.get("html_url"),
        "downloadUrl": data.get("download_url"),
    })


# ---------------------------------------------------------------------------
# Repos — commit diff
# ---------------------------------------------------------------------------

@router.get("/repos/{owner}/{repo}/diff")
async def get_commit_diff(
    owner: str, repo: str,
    token: str = Depends(_require_token),
    sha:   str = Query(...),
) -> JSONResponse:
    data   = await _github_get(f"/repos/{owner}/{repo}/commits/{sha}", token)
    commit = data.get("commit", {})
    return JSONResponse({
        "sha":     data["sha"],
        "message": commit.get("message", ""),
        "author":  commit.get("author", {}).get("name"),
        "date":    commit.get("author", {}).get("date"),
        "stats":   data.get("stats", {}),
        "files": [{
            "filename":         f["filename"],
            "status":           f["status"],
            "additions":        f["additions"],
            "deletions":        f["deletions"],
            "changes":          f["changes"],
            "patch":            f.get("patch"),
            "previousFilename": f.get("previous_filename"),
        } for f in data.get("files", [])],
    })


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.delete("/logout")
def github_logout(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    x_phoenix_session: Optional[str] = Header(default=None, alias="X-Phoenix-Session"),
) -> JSONResponse:
    raw = x_phoenix_session or phoenix_session
    if raw:
        sessions.delete(raw)
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response
