"""
Phoenix API â€” GitHub OAuth Router

Endpoints
---------
GET  /api/github/login
    Redirects the browser to GitHub's OAuth authorization page.
    Generates a one-time `state` parameter to prevent CSRF.

GET  /api/github/callback?code=â€¦&state=â€¦
    GitHub redirects here after the user grants permission.
    Exchanges the code for an access token, stores it server-side in a
    signed session cookie, then redirects the browser to /connect/callback
    so the React app can finish the flow.

GET  /api/github/me
    Returns the authenticated GitHub user's profile (login, name, avatar).
    Requires a valid session cookie.

GET  /api/github/repos
    Returns the authenticated user's repositories (all, sorted by push date).
    Requires a valid session cookie.

GET  /api/github/repos/{owner}/{repo}
    Returns metadata for a single repository.

GET  /api/github/repos/{owner}/{repo}/branches
    Returns the list of branches for a repository.

GET  /api/github/repos/{owner}/{repo}/commits
    Returns the latest commits on the default branch (or ?branch= override).

GET  /api/github/repos/{owner}/{repo}/contents
    Returns the file/directory listing at a given path (?path= default "/").

GET  /api/github/repos/{owner}/{repo}/diff
    Returns the unified diff for a specific commit (?sha= required).

DELETE /api/github/logout
    Clears the session cookie (sign-out).

Security
--------
- The GitHub access token is NEVER returned to the frontend.  It lives only
  in the server-side session store (in-process memory).
- The `state` parameter is a single-use, time-limited secret.
- The session cookie is HttpOnly, SameSite=Lax, signed with itsdangerous.
"""
from __future__ import annotations

import logging
import hashlib
import hmac
import json
import base64
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Body, Cookie, HTTPException, Query
from fastapi import Header, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..config import config
from ..repository_store import RepositoryStore
from ..analysis_store import AnalysisStore
from ..incident_store import IncidentStore
from ..session_store import COOKIE_NAME, SESSION_MAX_AGE, oauth_states, sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/github", tags=["github"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"

# Scopes: repo gives full access to public + private repos (read + write),
# which is what Phoenix needs to clone, read diffs, and open PRs.
OAUTH_SCOPES = "repo,read:user,admin:repo_hook,workflow"

PHOENIX_WORKFLOW_PATH = ".github/workflows/phoenix-monitor.yml"
PHOENIX_WORKFLOW = """name: Phoenix Monitor

on:
  push:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Set up Node
        if: hashFiles('package.json') != ''
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - name: Set up Python
        if: hashFiles('requirements.txt', 'pyproject.toml') != ''
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Validate repository
        shell: bash
        run: |
          set -e
          if [ -f package-lock.json ]; then
            npm ci
          elif [ -f package.json ]; then
            npm install
          fi
          if [ -f package.json ]; then
            node -e 'const p=require("./package.json"); if (p.scripts?.typecheck) process.exit(require("child_process").spawnSync("npm",["run","typecheck"],{stdio:"inherit"}).status ?? 1)'
            node -e 'const p=require("./package.json"); if (p.scripts?.lint) process.exit(require("child_process").spawnSync("npm",["run","lint"],{stdio:"inherit"}).status ?? 1)'
            node -e 'const p=require("./package.json"); if (p.scripts?.test) process.exit(require("child_process").spawnSync("npm",["test"],{stdio:"inherit"}).status ?? 1)'
            node -e 'const p=require("./package.json"); if (p.scripts?.build) process.exit(require("child_process").spawnSync("npm",["run","build"],{stdio:"inherit"}).status ?? 1)'
          elif [ -f requirements.txt ] || [ -f pyproject.toml ]; then
            python -m pip install --upgrade pip
            if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
            if [ -d tests ]; then pip install pytest; pytest -q; fi
          else
            echo "Phoenix could not detect a supported Node or Python project manifest."
            exit 1
          fi
          if [ -f Dockerfile ]; then docker build -t phoenix-monitor:ci .; fi
"""

# Where the frontend expects to land after a successful OAuth round-trip.
FRONTEND_CALLBACK = f"{config.FRONTEND_URL}/connect/callback"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_oauth_config() -> None:
    if not config.GITHUB_CLIENT_ID or not config.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=501,
            detail=(
                "GitHub OAuth is not configured. "
                "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in your .env file."
            ),
        )


async def _ensure_monitoring_workflow(repository: dict[str, Any], token: str) -> None:
    """Create Phoenix's generic CI workflow without overwriting repository code."""
    url = f"{GITHUB_API_BASE}/repos/{repository['owner']}/{repository['name']}/contents/{PHOENIX_WORKFLOW_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        existing = await client.get(url, headers=headers, params={"ref": repository["defaultBranch"]})
        if existing.status_code == 200:
            return
        if existing.status_code not in (404,):
            logger.error(
                "Could not inspect Phoenix workflow for %s: GitHub HTTP %s %s",
                repository["fullName"],
                existing.status_code,
                existing.text[:300],
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "GitHub rejected Phoenix workflow inspection "
                    f"(HTTP {existing.status_code}). Reauthorize GitHub and try again."
                ),
            )
        content = base64.b64encode(PHOENIX_WORKFLOW.encode("utf-8")).decode("ascii")
        payload: dict[str, Any] = {
            "message": "chore: configure Phoenix monitoring",
            "content": content,
            "branch": repository["defaultBranch"],
        }
        response = await client.put(url, headers=headers, json=payload)
    if response.status_code not in (200, 201):
        logger.error(
            "Could not install Phoenix workflow for %s: HTTP %s %s",
            repository["fullName"],
            response.status_code,
            response.text[:300],
        )
        if response.status_code == 404:
            detail = (
                "GitHub could not create the monitoring workflow. "
                "Reauthorize Phoenix with repository and workflow permissions, "
                "then select this repository again."
            )
        else:
            detail = (
                "GitHub rejected Phoenix workflow installation "
                f"(HTTP {response.status_code}). Check repository write permission "
                "and reauthorize GitHub."
            )
        raise HTTPException(status_code=502, detail=detail)


def _get_github_token(phoenix_session: Optional[str]) -> str:
    """Extract and validate the GitHub token from the session cookie."""
    if not phoenix_session:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /api/github/login first.")
    token = sessions.get_github_token(phoenix_session)
    if not token:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")
    return token


async def _github_get(path: str, token: str, **params: Any) -> Any:
    """
    Make an authenticated GET request to the GitHub API.
    Raises HTTPException on 4xx/5xx responses.
    """
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
        raise HTTPException(status_code=401, detail="GitHub token rejected. Please sign in again.")
    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error {response.status_code}: {response.text[:200]}",
        )
    return response.json()


# ---------------------------------------------------------------------------
# Step 1 â€” Redirect to GitHub
# ---------------------------------------------------------------------------


@router.get("/login")
def github_login() -> RedirectResponse:
    """
    Redirect the browser to GitHub's OAuth authorization page.
    Generates a fresh one-time state token for CSRF protection.
    """
    _require_oauth_config()
    state = oauth_states.issue()
    params = urlencode(
        {
            "client_id": config.GITHUB_CLIENT_ID,
            "redirect_uri": config.GITHUB_REDIRECT_URI,
            "scope": OAUTH_SCOPES,
            "state": state,
            "allow_signup": "true",
        }
    )
    return RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{params}", status_code=302)


# ---------------------------------------------------------------------------
# Step 2 â€” GitHub callback: exchange code â†’ token â†’ set cookie â†’ redirect
# ---------------------------------------------------------------------------


@router.get("/callback")
async def github_callback(
    code: str = Query(..., description="Temporary code from GitHub"),
    state: str = Query(..., description="CSRF state token"),
) -> RedirectResponse:
    """
    GitHub redirects here after the user authorises the app.
    Validates state, exchanges code for token, stores token in a signed
    HttpOnly session cookie, then sends the browser to the React callback page.
    """
    _require_oauth_config()

    # ---- CSRF check ----
    if not oauth_states.consume(state):
        logger.warning("OAuth callback: invalid or expired state parameter")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state. Please try signing in again.")

    # ---- Exchange code for access token ----
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": config.GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )

    if not token_response.is_success:
        logger.error("GitHub token exchange failed: %s", token_response.text)
        raise HTTPException(status_code=502, detail="Failed to exchange code for GitHub token.")

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        error = token_data.get("error_description", token_data.get("error", "unknown"))
        logger.error("GitHub token exchange returned no token: %s", error)
        raise HTTPException(status_code=502, detail=f"GitHub did not return an access token: {error}")

    logger.info("GitHub OAuth: token exchange successful")

    # ---- Store token in server-side session, get signed cookie value ----
    cookie_value = sessions.create(access_token)

    # ---- Redirect to the React callback route ----
    response = RedirectResponse(url=FRONTEND_CALLBACK, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        httponly=True,          # JS cannot read it
        samesite=config.SESSION_COOKIE_SAMESITE,
        max_age=SESSION_MAX_AGE,
        secure=config.SESSION_COOKIE_SECURE,
        path="/",
    )
    return response


# ---------------------------------------------------------------------------
# Step 3 â€” /me: who is signed in?
# ---------------------------------------------------------------------------


@router.get("/me")
async def github_me(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> JSONResponse:
    """
    Return the authenticated user's GitHub profile.
    The access token is never included in the response.
    """
    token = _get_github_token(phoenix_session)
    data = await _github_get("/user", token)
    return JSONResponse(
        {
            "login": data.get("login"),
            "name": data.get("name") or data.get("login"),
            "avatarUrl": data.get("avatar_url"),
            "company": data.get("company") or "",
            "email": data.get("email"),
            "publicRepos": data.get("public_repos", 0),
            "privateRepos": data.get("total_private_repos", 0),
        }
    )


@router.get("/selection")
async def get_selection(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> JSONResponse:
    """Return the repository currently connected to this user session."""
    token = _get_github_token(phoenix_session)
    profile = await _github_get("/user", token)
    selected = RepositoryStore.get_for_user(profile.get("login"))
    return JSONResponse({"repository": selected})


@router.put("/selection")
async def set_selection(
    repository: dict = Body(...),
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> JSONResponse:
    """Persist the repository whose incidents should appear in the dashboard."""
    token = _get_github_token(phoenix_session)
    required = ("id", "owner", "name", "fullName", "defaultBranch")
    if any(not repository.get(field) for field in required):
        raise HTTPException(
            status_code=422,
            detail=f"Repository selection requires: {', '.join(required)}",
        )
    selected = {
        "id": repository["id"],
        "owner": repository["owner"],
        "name": repository["name"],
        "fullName": repository["fullName"],
        "defaultBranch": repository["defaultBranch"],
    }
    remote = await _github_get(
        f"/repos/{selected['owner']}/{selected['name']}",
        token,
    )
    selected["defaultBranch"] = remote.get("default_branch", selected["defaultBranch"])
    profile = await _github_get("/user", token)
    connected = RepositoryStore.upsert(profile.get("login", ""), selected, token)
    sessions.set_selected_repo(phoenix_session, connected)
    await _ensure_workflow_webhook(selected, token)
    await _ensure_monitoring_workflow(selected, token)
    AnalysisStore.enqueue(selected["fullName"], profile.get("login", ""))
    return JSONResponse({"repository": connected})


async def _ensure_workflow_webhook(repository: dict[str, Any], token: str) -> None:
    """Subscribe the selected repository to completed GitHub Actions runs."""
    callback = f"{config.PHOENIX_PUBLIC_URL}/api/github/webhook"
    secret = config.PHOENIX_WEBHOOK_SECRET
    existing = await _github_get(
        f"/repos/{repository['owner']}/{repository['name']}/hooks",
        token,
        per_page=100,
    )
    for hook in existing:
        hook_config = hook.get("config") or {}
        if hook_config.get("url") == callback:
            hook_id = hook.get("id")
            if not hook_id:
                raise HTTPException(
                    status_code=502,
                    detail="GitHub returned a Phoenix webhook without an identifier.",
                )
            repair_url = f"{GITHUB_API_BASE}/repos/{repository['owner']}/{repository['name']}/hooks/{hook_id}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.patch(
                    repair_url,
                    headers={
                        "Authorization": f"******",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={
                        "active": True,
                        "events": ["workflow_run"],
                        "config": {
                            "url": callback,
                            "content_type": "json",
                            "secret": secret,
                            "insecure_ssl": "0",
                        },
                    },
                )
            if response.status_code != 200:
                logger.error(
                    "Could not repair GitHub webhook %s for %s: HTTP %s %s",
                    hook_id,
                    repository["fullName"],
                    response.status_code,
                    response.text[:300],
                )
                if response.status_code == 401:
                    detail = (
                        "GitHub rejected Phoenix webhook repair (HTTP 401). "
                        "Sign out of Phoenix, sign in again, and approve the "
                        "repository hook permission."
                    )
                else:
                    detail = (
                        "GitHub rejected Phoenix webhook repair "
                        f"(HTTP {response.status_code}). Reauthorize Phoenix and try again."
                    )
                raise HTTPException(
                    status_code=502,
                    detail=detail,
                )
            return
    url = f"{GITHUB_API_BASE}/repos/{repository['owner']}/{repository['name']}/hooks"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "name": "web",
                "active": True,
                "events": ["workflow_run"],
                "config": {
                    "url": callback,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )
    if response.status_code not in (201, 202):
        logger.error(
            "Could not register GitHub webhook for %s: HTTP %s %s",
            repository["fullName"],
            response.status_code,
            response.text[:300],
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "GitHub rejected Phoenix webhook registration "
                f"(HTTP {response.status_code}). Reauthorize GitHub with "
                "repository hook administration permission and try again."
            ),
        )


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
) -> dict[str, str]:
    """Turn failed completed GitHub Actions runs into agent jobs."""
    body = await request.body()
    expected = "sha256=" + hmac.new(
        config.PHOENIX_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
    if x_github_event != "workflow_run":
        return {"status": "ignored"}

    payload = json.loads(body)
    run = payload.get("workflow_run") or {}
    if payload.get("action") != "completed" or run.get("conclusion") in {"success", "skipped", "neutral"}:
        return {"status": "ignored"}
    repository = (payload.get("repository") or {}).get("full_name")
    commit = run.get("head_sha")
    branch = run.get("head_branch") or (payload.get("repository") or {}).get("default_branch")
    run_id = run.get("id")
    if not repository or not commit or not branch or not run_id:
        raise HTTPException(status_code=422, detail="Incomplete workflow_run payload")

    incident_id = IncidentStore.generate_incident_id()
    connection = RepositoryStore.get_for_repository(repository)
    IncidentStore.create_incident(
        incident_id=incident_id,
        source="github_ci",
        repository=repository,
        commit=commit,
        branch=branch,
        payload={
            "source": "github_ci",
            "repository": repository,
            "commit": commit,
            "branch": branch,
            "run_id": run_id,
            "run_url": run.get("html_url"),
            "workflow": (run.get("name") or "GitHub Actions"),
            "stage": "workflow_run",
            "logs": f"GitHub Actions run failed: {run.get('conclusion')}",
        },
        run_id=str(run_id),
        connected_github_login=connection.get("github_login") if connection else None,
    )
    if connection:
        IncidentStore.update_incident_status(
            incident_id,
            "queued_for_agent",
            message="Queued for the connected Phoenix agent",
        )
    return {"status": "queued", "incident_id": incident_id}


# ---------------------------------------------------------------------------
# Repos â€” list
# ---------------------------------------------------------------------------


@router.get("/repos")
async def list_repos(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> JSONResponse:
    """
    Return all repositories the authenticated user can access,
    sorted by most-recently pushed.
    """
    token = _get_github_token(phoenix_session)
    data = await _github_get(
        "/user/repos",
        token,
        visibility="all",
        affiliation="owner,collaborator,organization_member",
        sort="pushed",
        direction="desc",
        per_page=per_page,
        page=page,
    )
    repos = [
        {
            "id": r["id"],
            "owner": r["owner"]["login"],
            "name": r["name"],
            "fullName": r["full_name"],
            "private": r["private"],
            "language": r.get("language") or "Unknown",
            "pushedAt": r.get("pushed_at"),
            "defaultBranch": r.get("default_branch", "main"),
            "description": r.get("description") or "",
            "htmlUrl": r.get("html_url"),
            "cloneUrl": r.get("clone_url"),
            "stargazersCount": r.get("stargazers_count", 0),
        }
        for r in data
    ]
    return JSONResponse({"repos": repos, "page": page, "per_page": per_page})


# ---------------------------------------------------------------------------
# Repos â€” single repo metadata
# ---------------------------------------------------------------------------


@router.get("/repos/{owner}/{repo}")
async def get_repo(
    owner: str,
    repo: str,
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> JSONResponse:
    """Return metadata for a single repository."""
    token = _get_github_token(phoenix_session)
    data = await _github_get(f"/repos/{owner}/{repo}", token)
    return JSONResponse(
        {
            "id": data["id"],
            "owner": data["owner"]["login"],
            "name": data["name"],
            "fullName": data["full_name"],
            "private": data["private"],
            "language": data.get("language") or "Unknown",
            "pushedAt": data.get("pushed_at"),
            "defaultBranch": data.get("default_branch", "main"),
            "description": data.get("description") or "",
            "htmlUrl": data.get("html_url"),
            "cloneUrl": data.get("clone_url"),
        }
    )


# ---------------------------------------------------------------------------
# Repos â€” branches
# ---------------------------------------------------------------------------


@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(
    owner: str,
    repo: str,
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    per_page: int = Query(100, ge=1, le=100),
) -> JSONResponse:
    """Return all branches for a repository."""
    token = _get_github_token(phoenix_session)
    data = await _github_get(f"/repos/{owner}/{repo}/branches", token, per_page=per_page)
    branches = [
        {
            "name": b["name"],
            "sha": b["commit"]["sha"],
            "protected": b.get("protected", False),
        }
        for b in data
    ]
    return JSONResponse({"branches": branches})


# ---------------------------------------------------------------------------
# Repos â€” commits
# ---------------------------------------------------------------------------


@router.get("/repos/{owner}/{repo}/commits")
async def list_commits(
    owner: str,
    repo: str,
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    branch: Optional[str] = Query(None, description="Branch name; defaults to repo's default branch"),
    per_page: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
) -> JSONResponse:
    """Return recent commits, newest first."""
    token = _get_github_token(phoenix_session)
    params: dict[str, Any] = {"per_page": per_page, "page": page}
    if branch:
        params["sha"] = branch
    data = await _github_get(f"/repos/{owner}/{repo}/commits", token, **params)
    commits = [
        {
            "sha": c["sha"],
            "shortSha": c["sha"][:7],
            "message": c["commit"]["message"].split("\n")[0],
            "author": c["commit"]["author"]["name"],
            "authorEmail": c["commit"]["author"]["email"],
            "date": c["commit"]["author"]["date"],
            "htmlUrl": c.get("html_url"),
        }
        for c in data
    ]
    return JSONResponse({"commits": commits})


# ---------------------------------------------------------------------------
# Repos â€” file / directory contents
# ---------------------------------------------------------------------------


@router.get("/repos/{owner}/{repo}/contents")
async def get_contents(
    owner: str,
    repo: str,
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    path: str = Query("", description="Path within the repo; empty = root"),
    ref: Optional[str] = Query(None, description="Branch, tag, or commit SHA"),
) -> JSONResponse:
    """
    Return file or directory contents.
    For directories: returns a listing of entries.
    For files: returns name, path, size, encoding, and decoded content.
    """
    token = _get_github_token(phoenix_session)
    api_path = f"/repos/{owner}/{repo}/contents/{path}".rstrip("/")
    params: dict[str, Any] = {}
    if ref:
        params["ref"] = ref

    data = await _github_get(api_path, token, **params)

    # Directory listing
    if isinstance(data, list):
        entries = [
            {
                "name": e["name"],
                "path": e["path"],
                "type": e["type"],        # "file" | "dir" | "symlink"
                "size": e.get("size", 0),
                "sha": e["sha"],
                "htmlUrl": e.get("html_url"),
                "downloadUrl": e.get("download_url"),
            }
            for e in data
        ]
        return JSONResponse({"type": "directory", "path": path or "/", "entries": entries})

    # Single file
    import base64 as _b64
    content_raw = data.get("content", "")
    try:
        decoded = _b64.b64decode(content_raw).decode("utf-8", errors="replace")
    except Exception:
        decoded = None

    return JSONResponse(
        {
            "type": "file",
            "name": data["name"],
            "path": data["path"],
            "size": data.get("size", 0),
            "sha": data["sha"],
            "encoding": data.get("encoding"),
            "content": decoded,
            "htmlUrl": data.get("html_url"),
            "downloadUrl": data.get("download_url"),
        }
    )


# ---------------------------------------------------------------------------
# Repos â€” diff for a specific commit
# ---------------------------------------------------------------------------


@router.get("/repos/{owner}/{repo}/diff")
async def get_commit_diff(
    owner: str,
    repo: str,
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    sha: str = Query(..., description="Commit SHA to get the diff for"),
) -> JSONResponse:
    """Return the unified diff and file list for a single commit."""
    token = _get_github_token(phoenix_session)
    data = await _github_get(f"/repos/{owner}/{repo}/commits/{sha}", token)
    files = [
        {
            "filename": f["filename"],
            "status": f["status"],          # added | removed | modified | renamed
            "additions": f["additions"],
            "deletions": f["deletions"],
            "changes": f["changes"],
            "patch": f.get("patch"),         # unified diff string
            "previousFilename": f.get("previous_filename"),
        }
        for f in data.get("files", [])
    ]
    commit = data.get("commit", {})
    return JSONResponse(
        {
            "sha": data["sha"],
            "message": commit.get("message", ""),
            "author": commit.get("author", {}).get("name"),
            "date": commit.get("author", {}).get("date"),
            "stats": data.get("stats", {}),
            "files": files,
        }
    )


# ---------------------------------------------------------------------------
# Sign out
# ---------------------------------------------------------------------------


@router.delete("/logout")
def github_logout(
    phoenix_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> JSONResponse:
    """Clear the session cookie (sign out)."""
    if phoenix_session:
        sessions.delete(phoenix_session)
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response
