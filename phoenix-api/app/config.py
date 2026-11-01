"""
Phoenix API — Configuration

Loads all settings from environment variables.
Fail-fast on startup if required variables are missing.
"""
import os
from typing import Optional


class Config:
    """Central configuration from environment."""

    # MongoDB
    MONGO_URI: str = os.environ.get(
        "MONGO_URI", "mongodb://localhost:27017"
    )
    MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "phoenix")

    # Phoenix webhook authentication
    PHOENIX_WEBHOOK_SECRET: str = os.environ.get("PHOENIX_WEBHOOK_SECRET", "")
    if not PHOENIX_WEBHOOK_SECRET:
        raise ValueError(
            "PHOENIX_WEBHOOK_SECRET environment variable is required. "
            "Set it to a strong random string shared with GitHub Actions."
        )

    # LLM (Groq)
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    # GitHub (static PAT — used by the self-healing pipeline)
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO: str = os.environ.get("GITHUB_REPO", "")
    GITHUB_BASE_BRANCH: str = os.environ.get("GITHUB_BASE_BRANCH", "main")

    # GitHub OAuth App — used by /api/github/* endpoints.
    # Not required for the core incident pipeline; the endpoints return 501
    # gracefully when these are absent.
    GITHUB_CLIENT_ID: str = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.environ.get("GITHUB_CLIENT_SECRET", "")
    # Must match the callback URL registered in your GitHub OAuth App settings.
    GITHUB_REDIRECT_URI: str = os.environ.get(
        "GITHUB_REDIRECT_URI", "http://localhost:8000/api/github/callback"
    )
    # Public base URL of this API server (used for webhook registration).
    PHOENIX_PUBLIC_URL: str = os.environ.get("PHOENIX_PUBLIC_URL", "").rstrip("/")
    if not PHOENIX_PUBLIC_URL:
        # Derive from redirect URI only as a local-dev fallback
        PHOENIX_PUBLIC_URL = GITHUB_REDIRECT_URI.rsplit("/api/github/callback", 1)[0].rstrip("/")

    # Where the React frontend lives — used to build post-OAuth redirect URLs.
    FRONTEND_URL: str = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")

    # Secret used to sign session cookies.  Generate with: openssl rand -hex 32
    SESSION_SECRET_KEY: str = os.environ.get("SESSION_SECRET_KEY", "change-me-in-production")
    GITHUB_TOKEN_ENCRYPTION_KEY: str = os.environ.get(
        "GITHUB_TOKEN_ENCRYPTION_KEY", SESSION_SECRET_KEY
    )
    PHOENIX_AGENT_TOKEN: str = os.environ.get("PHOENIX_AGENT_TOKEN", "")

    # SameSite=None + Secure is required when the frontend and API are on
    # different origins (e.g. localhost:3000 → Render HTTPS).
    # Set SESSION_COOKIE_SAMESITE=none and SESSION_COOKIE_SECURE=true in .env
    # for cross-origin deployments; the auto-detection below handles local dev.
    SESSION_COOKIE_SAMESITE: str = os.environ.get(
        "SESSION_COOKIE_SAMESITE",
        "none" if os.environ.get("GITHUB_REDIRECT_URI", "").lower().startswith("https://") else "lax",
    ).lower()
    SESSION_COOKIE_SECURE: bool = os.environ.get(
        "SESSION_COOKIE_SECURE",
        "true" if os.environ.get("GITHUB_REDIRECT_URI", "").lower().startswith("https://") else "false",
    ).lower() in ("1", "true", "yes")

    # Git author identity (for commits)
    PHOENIX_GIT_AUTHOR_NAME: str = os.environ.get(
        "PHOENIX_GIT_AUTHOR_NAME", "Phoenix Bot"
    )
    PHOENIX_GIT_AUTHOR_EMAIL: str = os.environ.get(
        "PHOENIX_GIT_AUTHOR_EMAIL", "phoenix@example.com"
    )

    # Sandbox / validation
    PHOENIX_MAX_ATTEMPTS: int = int(os.environ.get("PHOENIX_MAX_ATTEMPTS", "2"))
    SANDBOX_RUN_DOCKER: bool = os.environ.get("SANDBOX_RUN_DOCKER", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    SANDBOX_SKIP_DOCKER_IF_UNAVAILABLE: bool = (
        os.environ.get("SANDBOX_SKIP_DOCKER_IF_UNAVAILABLE", "true").lower()
        in ("1", "true", "yes")
    )

    # Repository to heal (local clone path or remote URL)
    PHOENIX_REPO_PATH: str = os.environ.get(
        "PHOENIX_REPO_PATH", "/tmp/phoenix-repo"
    )

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # Optional: GitHub webhook signature verification
    # If set, verify X-Hub-Signature-256 header on workflow_run events
    VERIFY_GITHUB_SIGNATURE: bool = (
        os.environ.get("VERIFY_GITHUB_SIGNATURE", "true").lower()
        in ("1", "true", "yes")
    )


config = Config()
