"""
Phoenix Sandbox — Main Pipeline Orchestrator

SandboxPipeline is the single entry point for Person 4's module.
It wires all sub-components together into the complete flow:

    LLM PatchResult
         ↓
    Create temporary sandbox copy  (workspace.py)
         ↓
    Apply patch to sandbox         (patch_applicator.py)
         ↓
    Run lint / tests / Docker      (validator.py + docker_runner.py)
         ↓
    Check original failure resolved?
         ↓
    VALIDATED? ──NO──→ Reject (return PatchOutcome.validated=False)
         │
        YES
         ↓
    Apply patch to real repo       (git_manager.py)
    Create branch phoenix/fix/INC-XXX
    Commit + Push
         ↓
    Create GitHub Pull Request     (github_service.py)
         ↓
    Return PatchOutcome

Design principles
-----------------
- The sandbox copy is ALWAYS cleaned up (via context manager).
- The production repository is NEVER touched unless validation passes.
- If validation fails, NO branch, commit, or PR is created.
- All errors are caught and returned in PatchOutcome.error — the pipeline
  never crashes the Phoenix orchestrator.
- The pipeline publishes events to the EventBus if one is provided, so
  Person 5 can observe progress without polling.

Integration with the existing LLM engine
-----------------------------------------
The pipeline accepts an LLMEngineResult directly:

    from agent.ai.llm_engine import LLMEngine, EvidenceInput
    from agent.sandbox import SandboxPipeline

    engine = LLMEngine()
    llm_result = engine.run(evidence)

    pipeline = SandboxPipeline()
    outcome = pipeline.run(
        incident_id="INC-007",
        repo_path="/path/to/repo",
        llm_result=llm_result,
    )

Or with a PatchResult directly (for testing):

    outcome = pipeline.run_patch(
        incident_id="INC-007",
        repo_path="/path/to/repo",
        patch=patch_result,
        error_type="TypeError",
        error_message="unsupported operand...",
    )
"""
from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from agent.ai.llm_engine.engine import LLMEngineResult
from agent.ai.llm_engine.patch import PatchResult
from agent.sandbox.git_manager import create_branch_and_commit
from agent.sandbox.github_service import create_pull_request
from agent.sandbox.models import PatchOutcome, SandboxConfig, ValidationResult
from agent.sandbox.patch_applicator import apply_patch
from agent.sandbox.validator import validate_sandbox
from agent.sandbox.workspace import SandboxWorkspace

logger = logging.getLogger(__name__)


class SandboxPipeline:
    """
    Phoenix Sandbox Pipeline — the top-level orchestrator for Person 4's module.

    Construct once, call run() or run_patch() for each incident.

    Constructor kwargs are optional — all have sensible defaults read from
    environment variables (see agent/config/settings.py and .env.example).
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        # Git / GitHub config (all fall back to env vars)
        github_repo: str = "",          # "owner/repo"
        base_branch: str = "main",
        git_username: str = "",
        github_token: str = "",
        # EventBus for publishing sandbox events (optional)
        bus=None,
    ) -> None:
        self._config = config or _config_from_env()
        self._github_repo = github_repo or os.environ.get("GITHUB_REPO", "")
        self._base_branch = base_branch or os.environ.get("GITHUB_BASE_BRANCH", "main")
        self._git_username = git_username or os.environ.get("GIT_USERNAME", "")
        self._github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._bus = bus

        logger.info(
            "SandboxPipeline: initialised (repo=%s base=%s docker=%s)",
            self._github_repo or "<not set>",
            self._base_branch,
            self._config.run_docker,
        )

    # ------------------------------------------------------------------ #
    # Primary API — accepts LLMEngineResult                               #
    # ------------------------------------------------------------------ #

    def run(
        self,
        incident_id: str,
        repo_path: str | pathlib.Path,
        llm_result: LLMEngineResult,
    ) -> PatchOutcome:
        """
        Run the complete pipeline from an LLMEngineResult.

        Args:
            incident_id: The incident identifier (e.g. "INC-007").
            repo_path:   Absolute path to the local repository root.
            llm_result:  The result from LLMEngine.run().

        Returns:
            PatchOutcome — always returned, never raises.
        """
        if not llm_result.success or llm_result.patch is None:
            reason = llm_result.error or "LLM pipeline did not succeed."
            logger.error(
                "SandboxPipeline [%s]: aborting — %s", incident_id, reason
            )
            return PatchOutcome(
                incident_id=incident_id,
                validated=False,
                error=reason,
            )

        if llm_result.patch.is_empty:
            return PatchOutcome(
                incident_id=incident_id,
                validated=False,
                error="LLM returned an empty patch — nothing to validate.",
            )

        error_type = ""
        error_message = ""
        root_cause = ""
        if llm_result.evidence:
            error_type = llm_result.evidence.error_type
            error_message = llm_result.evidence.error_message
        if llm_result.diagnosis:
            root_cause = llm_result.diagnosis.root_cause

        return self.run_patch(
            incident_id=incident_id,
            repo_path=repo_path,
            patch=llm_result.patch,
            error_type=error_type,
            error_message=error_message,
            root_cause=root_cause,
        )

    # ------------------------------------------------------------------ #
    # Secondary API — accepts PatchResult directly (useful for testing)   #
    # ------------------------------------------------------------------ #

    def run_patch(
        self,
        incident_id: str,
        repo_path: str | pathlib.Path,
        patch: PatchResult,
        error_type: str = "",
        error_message: str = "",
        root_cause: str = "",
    ) -> PatchOutcome:
        """
        Run the pipeline with an explicit PatchResult.

        This is the lower-level entry point used by run() and also directly
        callable from tests or the orchestrator when the LLM result has
        already been unpacked.

        Args:
            incident_id:   Incident identifier.
            repo_path:     Absolute path to the local repository root.
            patch:         Validated PatchResult from the LLM engine.
            error_type:    Original exception type (for failure-resolved check).
            error_message: Original exception message.
            root_cause:    LLM root cause text (for PR body).

        Returns:
            PatchOutcome — always returned, never raises.
        """
        repo_path = pathlib.Path(repo_path).resolve()
        outcome = PatchOutcome(incident_id=incident_id)

        self._publish("SANDBOX_STARTED", incident_id)

        try:
            outcome = self._execute(
                incident_id=incident_id,
                repo_path=repo_path,
                patch=patch,
                error_type=error_type,
                error_message=error_message,
                root_cause=root_cause,
            )
        except Exception as exc:
            logger.exception(
                "SandboxPipeline [%s]: unhandled exception — %s", incident_id, exc
            )
            outcome = PatchOutcome(
                incident_id=incident_id,
                validated=False,
                error=f"Unhandled pipeline exception: {exc}",
            )
            self._publish("SANDBOX_FAILED", incident_id)
            return outcome

        if outcome.validated:
            self._publish("SANDBOX_VALIDATED", incident_id)
        else:
            self._publish("SANDBOX_REJECTED", incident_id)

        logger.info("SandboxPipeline: %s", outcome.summary())
        return outcome

    # ------------------------------------------------------------------ #
    # Internal execution (never raises)                                   #
    # ------------------------------------------------------------------ #

    def _execute(
        self,
        incident_id: str,
        repo_path: pathlib.Path,
        patch: PatchResult,
        error_type: str,
        error_message: str,
        root_cause: str,
    ) -> PatchOutcome:
        """
        Core execution flow. Always cleans up the sandbox even on failure.
        """

        # ============================================================== #
        # PART 1 — Create isolated sandbox copy                           #
        # ============================================================== #
        logger.info(
            "SandboxPipeline [%s]: creating sandbox from %s",
            incident_id,
            repo_path,
        )

        workspace = SandboxWorkspace.create(
            repo_root=repo_path,
            incident_id=incident_id,
            base_dir=self._config.sandbox_base_dir,
        )

        try:
            # ========================================================== #
            # PART 2 — Apply patch to sandbox copy                        #
            # ========================================================== #
            logger.info(
                "SandboxPipeline [%s]: applying %d patch(es)",
                incident_id,
                len(patch.patches),
            )
            app_result = apply_patch(patch, workspace)
            if not app_result.success:
                logger.error(
                    "SandboxPipeline [%s]: patch application failed — %s",
                    incident_id,
                    app_result.error,
                )
                return PatchOutcome(
                    incident_id=incident_id,
                    validated=False,
                    error=f"Patch application failed: {app_result.error}",
                )

            # ========================================================== #
            # PART 3–5 — Validate: lint / tests / Docker / failure check  #
            # ========================================================== #
            logger.info(
                "SandboxPipeline [%s]: running validation",
                incident_id,
            )
            validation = validate_sandbox(
                workspace=workspace,
                incident_id=incident_id,
                config=self._config,
                original_error_type=error_type,
                original_error_message=error_message,
            )

            # ========================================================== #
            # PART 6 — Decision                                           #
            # ========================================================== #
            if not validation.validated:
                logger.warning(
                    "SandboxPipeline [%s]: validation FAILED — %s",
                    incident_id,
                    validation.reason,
                )
                return PatchOutcome(
                    incident_id=incident_id,
                    validated=False,
                    validation=validation,
                    error=None,  # This is a validation rejection, not a pipeline error
                )

        finally:
            # Always clean up the sandbox — success or failure
            workspace.cleanup()

        # ================================================================== #
        # PART 7–9 — Only reached when validated=True                        #
        # ================================================================== #
        logger.info(
            "SandboxPipeline [%s]: validation PASSED — proceeding to Git",
            incident_id,
        )

        # PART 7 + 8 — Create branch, apply patch to real repo, commit, push
        git_result = create_branch_and_commit(
            repo_path=repo_path,
            incident_id=incident_id,
            patch=patch,
            base_branch=self._base_branch,
            git_username=self._git_username,
            git_token=self._github_token,
        )

        if not git_result.success:
            logger.error(
                "SandboxPipeline [%s]: Git step failed — %s",
                incident_id,
                git_result.error,
            )
            return PatchOutcome(
                incident_id=incident_id,
                validated=True,  # Validation passed, but Git failed
                validation=validation,
                git=git_result,
                error=f"Git step failed: {git_result.error}",
            )

        # PART 9 — Create Pull Request
        pr_result = create_pull_request(
            git_result=git_result,
            validation=validation,
            incident_id=incident_id,
            repo_full_name=self._github_repo,
            root_cause=root_cause,
            patch_explanation=patch.explanation,
            base_branch=self._base_branch,
            github_token=self._github_token,
        )

        if not pr_result.success:
            logger.warning(
                "SandboxPipeline [%s]: PR creation failed — %s (%s)",
                incident_id,
                pr_result.error,
                "branch was pushed" if git_result.remote_url else "branch kept locally, not pushed",
            )

        return PatchOutcome(
            incident_id=incident_id,
            validated=True,
            validation=validation,
            git=git_result,
            pull_request=pr_result,
            pull_request_url=pr_result.pr_url,
        )

    # ------------------------------------------------------------------ #
    # EventBus integration                                                  #
    # ------------------------------------------------------------------ #

    def _publish(self, event_type: str, incident_id: str) -> None:
        """Publish a sandbox event to the EventBus if one is attached."""
        if self._bus is None:
            return
        try:
            self._bus.publish(event_type, {"incident_id": incident_id})
        except Exception as exc:
            logger.debug(
                "SandboxPipeline: could not publish event %s — %s", event_type, exc
            )


# ============================================================================ #
# Configuration factory from environment                                         #
# ============================================================================ #

def _config_from_env() -> SandboxConfig:
    """
    Build a SandboxConfig from environment variables.

    Falls back to sensible defaults when variables are not set.
    """
    def _bool(key: str, default: bool) -> bool:
        val = os.environ.get(key, "").lower()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no"):
            return False
        return default

    def _int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, str(default)))
        except ValueError:
            return default

    return SandboxConfig(
        sandbox_base_dir=os.environ.get("SANDBOX_BASE_DIR", ""),
        docker_timeout_seconds=_int("SANDBOX_DOCKER_TIMEOUT", 180),
        container_startup_timeout=_int("SANDBOX_CONTAINER_STARTUP_TIMEOUT", 30),
        lint_timeout_seconds=_int("SANDBOX_LINT_TIMEOUT", 60),
        test_timeout_seconds=_int("SANDBOX_TEST_TIMEOUT", 120),
        run_lint=_bool("SANDBOX_RUN_LINT", True),
        run_tests=_bool("SANDBOX_RUN_TESTS", True),
        run_docker=_bool("SANDBOX_RUN_DOCKER", True),
        skip_docker_if_unavailable=_bool("SANDBOX_SKIP_DOCKER_IF_UNAVAILABLE", True),
    )
