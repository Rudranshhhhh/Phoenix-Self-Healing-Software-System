"""
Phoenix Sandbox — Data Models

All Pydantic models that flow through the sandbox pipeline.
These are the contracts between every sub-component and between this module
and the rest of Phoenix.

Hierarchy
---------
SandboxConfig      — per-run configuration (paths, timeouts, flags)
DockerResult       — result of building + running the Docker sandbox
ValidationResult   — aggregated lint/test/build/docker check outcome
GitResult          — branch + commit information after a successful push
PRResult           — Pull Request metadata returned from GitHub
PatchOutcome       — the single top-level result returned by SandboxPipeline.run()

All models are read-only after construction (frozen where appropriate).
They serialise cleanly to dict/JSON for persistence and logging.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================ #
# Configuration                                                                  #
# ============================================================================ #

class SandboxConfig(BaseModel):
    """
    Per-run sandbox configuration.

    Passed to SandboxPipeline.run() (or built from environment variables by
    the pipeline itself) to control all tunable aspects of the validation.
    """

    # ------------------------------------------------------------------ #
    # Paths                                                                #
    # ------------------------------------------------------------------ #
    # Base directory under which per-incident temp dirs are created.
    # Defaults to <system-tmp>/phoenix/
    sandbox_base_dir: str = Field(
        default="",
        description=(
            "Base temp directory. Empty string = use the OS default tmp dir "
            "with a phoenix/ subdirectory."
        ),
    )

    # ------------------------------------------------------------------ #
    # Validation targets                                                   #
    # ------------------------------------------------------------------ #
    # Relative paths inside the sandbox copy that should be linted.
    # Empty list = use the auto-detected target (usually "." or "sample-app").
    lint_targets: list[str] = Field(
        default_factory=list,
        description="Paths to pass to flake8. Empty = auto-detect.",
    )

    # Pytest test paths — empty = use pytest.ini testpaths or '.'
    test_paths: list[str] = Field(
        default_factory=list,
        description="Paths to pass to pytest. Empty = use pytest.ini defaults.",
    )

    # ------------------------------------------------------------------ #
    # Docker                                                               #
    # ------------------------------------------------------------------ #
    # Name of the Dockerfile relative to the sandbox root that will be
    # built. If empty, auto-detected (tries sample-app/Dockerfile first,
    # then root Dockerfile).
    dockerfile_path: str = Field(
        default="",
        description="Relative path to the Dockerfile inside the sandbox.",
    )

    # Container startup timeout (seconds) — how long we wait for /health
    container_startup_timeout: int = Field(
        default=30,
        description="Seconds to wait for the container /health to become 200.",
    )

    # Overall Docker validation timeout (build + run combined, seconds)
    docker_timeout_seconds: int = Field(
        default=180,
        description="Total seconds allowed for Docker build + run validation.",
    )

    # ------------------------------------------------------------------ #
    # Lint / test timeouts                                                  #
    # ------------------------------------------------------------------ #
    lint_timeout_seconds: int = Field(
        default=60,
        description="Max seconds for the flake8 lint step.",
    )
    test_timeout_seconds: int = Field(
        default=120,
        description="Max seconds for the pytest step.",
    )

    # ------------------------------------------------------------------ #
    # Feature flags                                                        #
    # ------------------------------------------------------------------ #
    run_lint: bool = Field(default=True, description="Whether to run flake8.")
    run_tests: bool = Field(default=True, description="Whether to run pytest.")
    run_docker: bool = Field(
        default=True,
        description=(
            "Whether to build+run the Docker sandbox. "
            "Can be disabled for lightweight local dev."
        ),
    )

    # Skip Docker if the Docker daemon is unavailable (e.g. CI without DinD).
    skip_docker_if_unavailable: bool = Field(
        default=True,
        description=(
            "When True, a missing/unreachable Docker daemon downgrades the "
            "Docker step to a warning instead of a hard failure."
        ),
    )


# ============================================================================ #
# Docker Result                                                                  #
# ============================================================================ #

class DockerResult(BaseModel):
    """
    Result of building and running the Docker sandbox.

    A None value for a field means the corresponding step was not reached
    (e.g. container_started is None when build_passed is False).
    """

    build_passed: bool = False
    container_started: bool = False
    health_check_passed: bool = False

    # Raw capture from Docker
    build_stdout: str = ""
    build_stderr: str = ""
    container_stdout: str = ""
    container_stderr: str = ""

    # Exit codes — None means the step never ran
    build_exit_code: Optional[int] = None
    container_exit_code: Optional[int] = None

    # Duration
    build_duration_seconds: float = 0.0
    run_duration_seconds: float = 0.0

    # Transient image/container names used during this run
    image_tag: str = ""
    container_name: str = ""

    # Whether docker was skipped entirely (daemon unavailable + config allows it)
    skipped: bool = False
    skip_reason: str = ""

    # Human-readable summary of what failed (empty on success)
    failure_reason: str = ""


# ============================================================================ #
# Validation Result                                                              #
# ============================================================================ #

class ValidationResult(BaseModel):
    """
    Aggregated result of all validation steps.

    This is the structured evidence passed back to the orchestrator
    and embedded in the Pull Request body.
    """

    incident_id: str = Field(description="The incident this validation targets.")

    # Individual step outcomes
    build_passed: bool = False
    lint_passed: bool = False
    tests_passed: bool = False
    container_started: bool = False
    original_failure_resolved: bool = False

    # Derived — set by _compute_validated()
    validated: bool = False

    # Step details
    lint_stdout: str = ""
    lint_stderr: str = ""
    lint_exit_code: Optional[int] = None

    test_stdout: str = ""
    test_stderr: str = ""
    test_exit_code: Optional[int] = None

    docker: Optional[DockerResult] = None

    # Overall failure / success description
    reason: str = ""

    # Timing
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    def compute_validated(self) -> "ValidationResult":
        """
        Derive `validated` from the individual step outcomes and set `reason`.

        Validation passes when ALL of:
          - build_passed (lint + pytest ran without errors)
          - lint_passed
          - tests_passed
          - original_failure_resolved

        Docker container check is desirable but optional when Docker was
        skipped (see DockerResult.skipped).

        Returns self for chaining.
        """
        docker_ok = True
        if self.docker and not self.docker.skipped:
            docker_ok = self.docker.container_started

        self.validated = (
            self.build_passed
            and self.lint_passed
            and self.tests_passed
            and self.original_failure_resolved
            and docker_ok
        )

        if self.validated:
            self.reason = "All validation checks passed."
        else:
            failures = []
            if not self.build_passed:
                failures.append("build failed")
            if not self.lint_passed:
                failures.append("lint failed")
            if not self.tests_passed:
                failures.append("tests failed")
            if not self.original_failure_resolved:
                failures.append("original failure still present")
            if not docker_ok:
                failures.append("container did not start")
            self.reason = "Patch rejected — " + ", ".join(failures) + "."

        self.completed_at = datetime.now(timezone.utc)
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

        return self

    def to_pr_section(self) -> str:
        """Return a Markdown table of validation results for the PR body."""
        def _icon(passed: bool) -> str:
            return "✅ PASS" if passed else "❌ FAIL"

        docker_status = "N/A (skipped)"
        if self.docker:
            if self.docker.skipped:
                docker_status = f"⚠️ SKIPPED ({self.docker.skip_reason})"
            else:
                docker_status = _icon(self.docker.container_started)

        return (
            f"| Step | Result |\n"
            f"| :--- | :--- |\n"
            f"| Build | {_icon(self.build_passed)} |\n"
            f"| Lint | {_icon(self.lint_passed)} |\n"
            f"| Tests | {_icon(self.tests_passed)} |\n"
            f"| Container | {docker_status} |\n"
            f"| Original failure resolved | {_icon(self.original_failure_resolved)} |\n"
        )


# ============================================================================ #
# Git Result                                                                     #
# ============================================================================ #

class GitResult(BaseModel):
    """Result of the branch-create + commit + push step."""

    success: bool = False
    branch_name: str = ""    # e.g. phoenix/fix/INC-007
    commit_sha: str = ""     # full SHA of the created commit
    commit_message: str = ""
    remote_url: str = ""     # the remote the branch was pushed to
    error: Optional[str] = None


# ============================================================================ #
# PR Result                                                                      #
# ============================================================================ #

class PRResult(BaseModel):
    """Metadata about the GitHub Pull Request that was created."""

    success: bool = False
    pr_number: Optional[int] = None
    pr_url: str = ""
    title: str = ""
    base_branch: str = "main"
    head_branch: str = ""
    error: Optional[str] = None


# ============================================================================ #
# Top-level Pipeline Output                                                      #
# ============================================================================ #

class PatchOutcome(BaseModel):
    """
    The single top-level result returned by SandboxPipeline.run().

    This is the contract between Person 4's module and Person 5 (orchestrator).

    Fields
    ------
    incident_id          The incident that triggered this pipeline run.
    validated            True when the patch passed ALL validation steps.
    validation           Detailed per-step validation result.
    git                  Branch + commit info (only set when validated=True).
    pull_request         PR metadata (only set when PR was created).
    pull_request_url     Convenience shortcut to the PR URL.
    error                Top-level error message if the pipeline itself failed.
    ran_at               UTC timestamp of when the pipeline started.
    """

    incident_id: str
    validated: bool = False

    # Detailed results — always populated
    validation: Optional[ValidationResult] = None

    # Only populated on success
    git: Optional[GitResult] = None
    pull_request: Optional[PRResult] = None

    # Convenience shortcut
    pull_request_url: str = ""

    # Pipeline-level error (not a validation failure, but an unexpected crash)
    error: Optional[str] = None

    ran_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def summary(self) -> str:
        """Return a one-paragraph human-readable summary for logging."""
        if self.error and not self.validated:
            return (
                f"SandboxPipeline [{self.incident_id}] — PIPELINE ERROR: {self.error}"
            )
        if not self.validated:
            reason = (
                self.validation.reason if self.validation else "no validation performed"
            )
            return (
                f"SandboxPipeline [{self.incident_id}] — REJECTED: {reason}"
            )
        pr_info = (
            f" PR: {self.pull_request_url}" if self.pull_request_url else " (no PR)"
        )
        git_info = (
            f" branch={self.git.branch_name} commit={self.git.commit_sha[:7]}"
            if self.git
            else ""
        )
        return (
            f"SandboxPipeline [{self.incident_id}] — VALIDATED ✓"
            f"{git_info}{pr_info}"
        )
