"""
Phoenix API — Main Orchestrator

Central pipeline: evidence → LLM → sandbox → git → PR
"""
import logging
import os
import pathlib
import subprocess
from typing import Any, Dict, Optional

from .classifier import FailureClassifier
from .config import config
from .evidence import (
    extract_evidence_from_ci_payload,
    extract_evidence_from_docker_incident,
)
from .incident_store import IncidentStore

logger = logging.getLogger(__name__)


class PhoenixOrchestrator:
    """
    Main orchestration service.
    Processes an incident through the full pipeline:
      1. Classify (code vs non-code)
      2. Extract evidence
      3. LLM diagnosis + patch
      4. Sandbox validation
      5. Git branch + commit + push
      6. GitHub PR creation
    """

    def __init__(self):
        # LLM and Sandbox will be imported/initialized on-demand
        # to avoid hard dependency issues during startup
        self.llm_engine = None
        self.sandbox_pipeline = None

    def _get_llm_engine(self):
        """Lazily initialize LLM engine."""
        if self.llm_engine is None:
            try:
                from agent.ai.llm_engine import LLMEngine
                self.llm_engine = LLMEngine()
            except Exception as exc:
                logger.error("Failed to initialize LLM engine: %s", exc)
                raise
        return self.llm_engine

    def _get_sandbox_pipeline(self):
        """Lazily initialize Sandbox pipeline."""
        if self.sandbox_pipeline is None:
            try:
                from agent.sandbox import SandboxPipeline
                from agent.sandbox.models import SandboxConfig

                cfg = SandboxConfig(
                    sandbox_base_dir="/tmp/phoenix/sandbox",
                    docker_timeout_seconds=180,
                    container_startup_timeout=30,
                    lint_timeout_seconds=60,
                    test_timeout_seconds=120,
                    run_lint=True,
                    run_tests=True,
                    run_docker=config.SANDBOX_RUN_DOCKER,
                    skip_docker_if_unavailable=config.SANDBOX_SKIP_DOCKER_IF_UNAVAILABLE,
                )
                self.sandbox_pipeline = SandboxPipeline(
                    config=cfg,
                    github_repo=config.GITHUB_REPO,
                    base_branch=config.GITHUB_BASE_BRANCH,
                    github_token=config.GITHUB_TOKEN,
                )
            except Exception as exc:
                logger.error("Failed to initialize Sandbox pipeline: %s", exc)
                raise
        return self.sandbox_pipeline

    def process_incident(self, incident_id: str) -> Dict[str, Any]:
        """
        Main entry point: process an incident through the full pipeline.
        Updates the incident in MongoDB at each step.
        Returns the final incident document.
        """
        logger.info("Starting pipeline for %s", incident_id)

        incident = IncidentStore.get_incident(incident_id)
        if not incident:
            logger.error("Incident %s not found", incident_id)
            return {}

        payload = incident.get("payload", {})
        source = incident.get("source")

        try:
            # Step 1: Classify failure
            error_type = payload.get("error_type", "Unknown")
            error_message = payload.get("error_message", "")
            logs = payload.get("logs", "")

            classification, reason = FailureClassifier.classify(
                error_type, error_message, logs
            )
            if classification == "non_code":
                logger.info(
                    "%s — non-code failure, marking IGNORED: %s",
                    incident_id,
                    reason,
                )
                IncidentStore.update_incident_status(
                    incident_id,
                    "ignored",
                    message=reason,
                )
                return incident

            # Step 2: Extract evidence
            logger.info("%s — extracting evidence", incident_id)
            IncidentStore.update_incident_status(
                incident_id, "diagnosing", message="Extracting evidence"
            )

            if source == "github_ci":
                evidence = extract_evidence_from_ci_payload(payload)
            elif source == "docker_runtime":
                evidence = extract_evidence_from_docker_incident(payload)
            else:
                raise ValueError(f"Unknown source: {source}")

            if not evidence:
                raise RuntimeError("Evidence extraction failed")

            # Step 3: LLM diagnosis + patch generation
            logger.info("%s — running LLM engine", incident_id)
            llm_engine = self._get_llm_engine()
            llm_result = llm_engine.run(evidence)

            if not llm_result.success or llm_result.patch is None:
                reason = llm_result.error or "LLM pipeline failed"
                logger.warning("%s — LLM failed: %s", incident_id, reason)
                IncidentStore.set_error(
                    incident_id, "analysis_failed", reason
                )
                return IncidentStore.get_incident(incident_id)

            if llm_result.patch.is_empty:
                logger.warning("%s — LLM returned empty patch", incident_id)
                IncidentStore.set_error(
                    incident_id, "patch_failed", "LLM returned empty patch"
                )
                return IncidentStore.get_incident(incident_id)

            logger.info(
                "%s — patch generated with %d file(s)",
                incident_id,
                len(llm_result.patch.patches),
            )
            IncidentStore.update_incident_status(
                incident_id, "fix_proposed", message="Patch generated"
            )

            # Step 4: Sandbox validation
            logger.info("%s — starting sandbox validation", incident_id)
            IncidentStore.update_incident_status(
                incident_id, "validating", message="Running tests in sandbox"
            )

            # Get the repository path (must be a local clone)
            repo_path = pathlib.Path(config.PHOENIX_REPO_PATH).resolve()
            if not repo_path.exists():
                raise RuntimeError(
                    f"Repository not found at {repo_path}. "
                    f"Set PHOENIX_REPO_PATH to a valid local clone."
                )

            # Ensure the repo is checked out to the failing commit
            self._checkout_commit(repo_path, incident["commit"])

            # Run sandbox
            sandbox_pipeline = self._get_sandbox_pipeline()
            outcome = sandbox_pipeline.run(
                incident_id=incident_id,
                repo_path=repo_path,
                llm_result=llm_result,
            )

            # Store validation result
            if outcome.validation:
                IncidentStore.set_validation_result(
                    incident_id,
                    outcome.validation.model_dump(),
                )

            if not outcome.validated:
                reason = (
                    outcome.validation.reason
                    if outcome.validation
                    else (outcome.error or "Validation failed")
                )
                logger.warning("%s — validation failed: %s", incident_id, reason)
                IncidentStore.set_error(incident_id, "validation_failed", reason)
                # GATE: SandboxPipeline ensures NO git/PR operations occur when validated=false
                # See agent/sandbox/pipeline.py lines 323-330 — validation gate returns early
                # Result: No branch created, no commit, no push, no PR for failed patches
                return IncidentStore.get_incident(incident_id)

            # Step 5: Git branch, commit, push, PR already done by SandboxPipeline
            # Just store the results
            if outcome.git and outcome.git.success:
                IncidentStore.set_git_info(
                    incident_id,
                    branch=outcome.git.branch_name,
                    commit_sha=outcome.git.commit_sha,
                    pr_url=outcome.pull_request_url if outcome.pull_request else None,
                    pr_number=outcome.pull_request.pr_number
                    if outcome.pull_request
                    else None,
                )
                status = "pr_opened" if outcome.pull_request_url else "validated"
                IncidentStore.update_incident_status(
                    incident_id,
                    status,
                    message=f"Fix validated and PR created: {outcome.pull_request_url}",
                )
            else:
                reason = (
                    outcome.git.error
                    if outcome.git
                    else (outcome.error or "Git/PR step failed")
                )
                logger.error("%s — Git/PR step failed: %s", incident_id, reason)
                IncidentStore.set_error(incident_id, "git_failed", reason)

            logger.info("%s — pipeline complete, status: %s", incident_id, outcome.summary())
            return IncidentStore.get_incident(incident_id)

        except Exception as exc:
            logger.exception("%s — pipeline failed: %s", incident_id, exc)
            IncidentStore.set_error(
                incident_id,
                "pipeline_error",
                str(exc),
            )
            return IncidentStore.get_incident(incident_id)

    @staticmethod
    def _checkout_commit(repo_path: pathlib.Path, commit_sha: str) -> None:
        """
        Use `git checkout` to ensure the repo is at the specified commit.
        """
        try:
            subprocess.run(
                ["git", "checkout", commit_sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=30,
            )
            logger.info("Checked out commit %s", commit_sha[:7])
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to checkout commit %s: %s",
                commit_sha[:7],
                exc.stderr.decode() if exc.stderr else exc,
            )
            raise RuntimeError(f"Cannot checkout commit {commit_sha}: {exc}") from exc
