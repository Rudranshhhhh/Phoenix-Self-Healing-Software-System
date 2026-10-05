"""
Phoenix Agent — Application Settings

Single source of truth for all runtime configuration.
Values are read from environment variables via Pydantic BaseSettings.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All Phoenix Agent configuration — loaded from environment variables.
    Defaults are suitable for local Docker Compose development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # MongoDB                                                              #
    # ------------------------------------------------------------------ #
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "phoenix"

    # ------------------------------------------------------------------ #
    # Grok AI                                                              #
    # ------------------------------------------------------------------ #
    grok_api_key: str = ""
    grok_model: str = "grok-3-mini"
    grok_enabled: bool = True
    grok_timeout_seconds: int = 15

    # ------------------------------------------------------------------ #
    # Backend Reporter                                                     #
    # ------------------------------------------------------------------ #
    backend_url: str = "http://phoenix-backend:5000"

    # ------------------------------------------------------------------ #
    # Docker                                                               #
    # ------------------------------------------------------------------ #
    docker_socket: str = "unix:///var/run/docker.sock"

    # ------------------------------------------------------------------ #
    # Per-collector poll intervals (seconds)                              #
    # ------------------------------------------------------------------ #
    poll_docker_seconds: int = 2
    poll_health_seconds: int = 5
    poll_db_seconds: int = 10
    poll_redis_seconds: int = 10
    poll_logs_seconds: int = 20

    # ------------------------------------------------------------------ #
    # Recovery & Escalation                                               #
    # ------------------------------------------------------------------ #
    escalation_threshold: int = 3
    recovery_timeout_seconds: int = 60
    health_retry_attempts: int = 5
    health_retry_delay_seconds: float = 3.0

    # ------------------------------------------------------------------ #
    # Sample App / Monitored Services                                     #
    # ------------------------------------------------------------------ #
    sample_backend_url: str = "http://sample-backend:8080"
    sample_backend_container: str = "phoenix-sample-backend-1"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "sampleuser"
    postgres_password: str = "samplepassword"
    postgres_db: str = "sampledb"

    redis_host: str = "redis"
    redis_port: int = 6379

    # ------------------------------------------------------------------ #
    # Detection Thresholds                                                #
    # ------------------------------------------------------------------ #
    cpu_threshold_percent: float = 85.0
    memory_threshold_percent: float = 90.0
    health_latency_threshold_ms: float = 5000.0
    restart_count_delta_threshold: int = 3
    log_tail_lines: int = 50

    # ------------------------------------------------------------------ #
    # Sandbox / Validation / Git (Person 4)                               #
    # ------------------------------------------------------------------ #

    # Base directory for temporary sandbox copies.
    # Empty string = OS default temp dir / phoenix/
    sandbox_base_dir: str = ""

    # Docker validation timeouts (seconds)
    sandbox_docker_timeout: int = 180
    sandbox_container_startup_timeout: int = 30

    # Lint / test step timeouts (seconds)
    sandbox_lint_timeout: int = 60
    sandbox_test_timeout: int = 120

    # Feature flags — set to False to skip steps (e.g. in lightweight CI)
    sandbox_run_lint: bool = True
    sandbox_run_tests: bool = True
    sandbox_run_docker: bool = True
    sandbox_skip_docker_if_unavailable: bool = True

    # Git / GitHub
    # The full GitHub repository name: "owner/repo"
    github_repo: str = ""
    # The target branch for PRs (default: main)
    github_base_branch: str = "main"
    # GitHub Personal Access Token — required for branch push + PR creation
    github_token: str = ""
    # Git username for HTTPS push (optional — PAT alone is sufficient for GitHub)
    git_username: str = ""


# Singleton — import and use directly
settings = Settings()
