"""
Phoenix API — GitHub OAuth Router

Endpoints
---------
GET  /api/github/login
    Redirects the browser to GitHub's OAuth authorization page.
    Generates a one-time `state` parameter to prevent CSRF.

GET  /api/github/callback?code=…&state=…
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
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from ..config import config
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
OAUTH_SCOPES = "repo,read:user"

# Where the frontend expects to land after a successful OAuth round-trip.
FRONTEND_CALLBACK = "http://localhost:3000/connect/callback"

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
# Step 1 — Redirect to GitHub
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
# Step 2 — GitHub callback: exchange code → token → set cookie → redirect
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
        samesite="lax",         # CSRF protection — works with redirect flows
        max_age=SESSION_MAX_AGE,
        secure=False,           # set to True in production (HTTPS)
        path="/",
    )
    return response


# ---------------------------------------------------------------------------
# Step 3 — /me: who is signed in?
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


# ---------------------------------------------------------------------------
# Repos — list
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
# Repos — single repo metadata
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
# Repos — branches
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
# Repos — commits
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
# Repos — file / directory contents
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
# Repos — diff for a specific commit
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
