"""
Phoenix — Code Patch Engine

Bridges the existing Phoenix runtime pipeline with Person 4's sandbox module.

Subscribes to: INCIDENT_DIAGNOSED (published by DiagnosisEngine)
Publishes:     SANDBOX_VALIDATED, SANDBOX_REJECTED, SANDBOX_FAILED,
               SANDBOX_BRANCH_PUSHED, SANDBOX_PR_CREATED

Pipeline triggered on each INCIDENT_DIAGNOSED event:
  1. Convert the Incident into an EvidenceInput for the LLM engine.
  2. Run LLMEngine.run() → DiagnosisResult + PatchResult.
  3. Pass PatchResult to SandboxPipeline.run_patch().
  4. Publish the outcome event back onto the EventBus.
  5. Attach the PatchOutcome to the Incident for downstream reporting.

Design notes
------------
- The LLM engine call and sandbox validation are run in a background
  thread so they do not block the EventBus publisher's thread
  (both operations can take 30–180 seconds).
- Each incident gets exactly one code-patch attempt. If the LLM or
  sandbox fails, the Incident is not modified beyond logging.
- The repo_path defaults to the workspace root (the directory where
  Phoenix itself is running). This can be overridden via constructor
  argument or PHOENIX_REPO_PATH environment variable.
- CodePatchEngine is only activated when a GROQ_API_KEY is set in
  the environment. Without a key it logs a warning and does nothing.
- This engine is intentionally separate from DiagnosisEngine — it does
  not replace or alter the existing infra-level diagnosis flow.
"""
from __future__ import annotations

import logging
import os
import pathlib
import threading
from typing import Optional

from agent.ai.llm_engine import EvidenceInput, LLMEngine
from agent.config.settings import settings
from agent.events.bus import EventBus
from agent.events.event_types import (
    INCIDENT_DIAGNOSED,
    SANDBOX_BRANCH_PUSHED,
    SANDBOX_FAILED,
    SANDBOX_PR_CREATED,
    SANDBOX_REJECTED,
    SANDBOX_VALIDATED,
)
from agent.events.incident import Incident
from agent.sandbox.models import PatchOutcome, SandboxConfig
from agent.sandbox.pipeline import SandboxPipeline

logger = logging.getLogger(__name__)


class CodePatchEngine:
    """
    Subscribes to INCIDENT_DIAGNOSED and drives the full
    LLM → Sandbox → Validate → Branch → PR pipeline in a background thread.

    Constructor
    -----------
    bus          The shared EventBus instance.
    repo_path    Absolute path to the local repository root.
                 Defaults to PHOENIX_REPO_PATH env var, or the current
                 working directory.
    llm_engine   Optional pre-built LLMEngine (injected in tests).
    pipeline     Optional pre-built SandboxPipeline (injected in tests).
    enabled      If False, the engine registers but silently skips all events.
                 Useful for disabling the patch flow without changing main.py.
    """

    def __init__(
        self,
        bus: EventBus,
        repo_path: str | pathlib.Path = "",
        llm_engine: Optional[LLMEngine] = None,
        pipeline: Optional[SandboxPipeline] = None,
        enabled: bool = True,
    ) -> None:
        self._bus = bus
        self._repo_path = pathlib.Path(
            repo_path
            or os.environ.get("PHOENIX_REPO_PATH", "")
            or pathlib.Path.cwd()
        ).resolve()
        self._enabled = enabled and bool(
            os.environ.get("GROQ_API_KEY") or settings.github_token
        )

        # Lazy-initialise the LLM engine only when enabled (avoids import
        # errors if openai is not installed in a test environment)
        self._llm_engine = llm_engine
        self._pipeline = pipeline or _build_pipeline(bus)

        bus.subscribe(INCIDENT_DIAGNOSED, self.on_incident_diagnosed)

        if self._enabled:
            logger.info(
                "CodePatchEngine: initialised — repo=%s github=%s",
                self._repo_path,
                settings.github_repo or "<not set>",
            )
        else:
            logger.warning(
                "CodePatchEngine: GROQ_API_KEY / GITHUB_TOKEN not set — "
                "code patch pipeline disabled. Set these vars to enable it."
            )

    # ------------------------------------------------------------------ #
    # EventBus handler                                                     #
    # ------------------------------------------------------------------ #

    def on_incident_diagnosed(self, incident: Incident) -> None:
        """
        Called synchronously by the EventBus when INCIDENT_DIAGNOSED fires.

        Dispatches the actual work to a daemon thread so the EventBus thread
        is never blocked by LLM calls or Docker operations.
        """
        if not self._enabled:
            return

        t = threading.Thread(
            target=self._run_patch_pipeline,
            args=(incident,),
            daemon=True,
            name=f"code-patch-{incident.incident_id[:8]}",
        )
        t.start()

    # ------------------------------------------------------------------ #
    # Background thread work                                               #
    # ------------------------------------------------------------------ #

    def _run_patch_pipeline(self, incident: Incident) -> None:
        """
        Full pipeline executed in a background daemon thread:
          1. Build EvidenceInput from the Incident.
          2. Run LLMEngine to get a PatchResult.
          3. Run SandboxPipeline to validate + branch + PR.
          4. Publish the result event.
        """
        inc_id = incident.incident_id

        try:
            # Step 1 — Build evidence from the Incident
            evidence = _incident_to_evidence(incident)
            if evidence is None:
                logger.info(
                    "CodePatchEngine [%s]: no code-level evidence available "
                    "(infra-only incident) — skipping patch pipeline",
                    inc_id,
                )
                return

            # Step 2 — Run LLM engine
            llm_engine = self._llm_engine or LLMEngine()
            logger.info("CodePatchEngine [%s]: running LLM engine", inc_id)
            llm_result = llm_engine.run(evidence)

            if not llm_result.success or llm_result.patch is None:
                logger.warning(
                    "CodePatchEngine [%s]: LLM engine did not produce a patch — %s",
                    inc_id,
                    llm_result.error,
                )
                self._bus.publish(SANDBOX_FAILED, {"incident_id": inc_id})
                return

            if llm_result.patch.is_empty:
                logger.warning(
                    "CodePatchEngine [%s]: LLM returned an empty patch — skipping",
                    inc_id,
                )
                self._bus.publish(SANDBOX_REJECTED, {"incident_id": inc_id})
                return

            # Step 3 — Sandbox validation + Git + PR
            logger.info(
                "CodePatchEngine [%s]: starting sandbox pipeline", inc_id
            )
            outcome: PatchOutcome = self._pipeline.run(
                incident_id=inc_id,
                repo_path=self._repo_path,
                llm_result=llm_result,
            )

            # Step 4 — Publish outcome events and log
            _publish_outcome_events(self._bus, outcome)
            _log_outcome(inc_id, outcome)

        except Exception as exc:
            logger.exception(
                "CodePatchEngine [%s]: unhandled exception in patch pipeline — %s",
                inc_id,
                exc,
            )
            self._bus.publish(SANDBOX_FAILED, {"incident_id": inc_id})


# ============================================================================ #
# Helper functions                                                               #
# ============================================================================ #

def _incident_to_evidence(incident: Incident) -> Optional[EvidenceInput]:
    """
    Convert a Phoenix Incident into an EvidenceInput for the LLM engine.

    Returns None when the incident does not contain enough code-level context
    to be useful (e.g. pure infra failures like HIGH_CPU).

    For the MVP, we construct evidence from the log_errors captured by the
    LogsCollector and the incident's root_cause + failure_type. This is
    deliberately lightweight — a richer evidence builder can replace this
    function in a later sprint without changing the pipeline.
    """
    snapshot = incident.metrics_snapshot
    log_errors: list[str] = snapshot.log_errors if snapshot else []

    if not log_errors and not incident.root_cause:
        return None

    # Try to extract a Python exception type from log lines
    error_type = "RuntimeError"
    error_message = incident.root_cause or "Unspecified runtime failure"
    relevant_code = None
    stack_trace = None

    for line in log_errors:
        # Look for Python exception patterns in log output
        if "Error:" in line or "Exception:" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                error_type = parts[0].strip().split()[-1]  # last word before ":"
                error_message = parts[1].strip()
                stack_trace = "\n".join(log_errors)
                break
        if "Traceback" in line:
            stack_trace = "\n".join(log_errors)

    # Relevant code from grok_summary if available
    if incident.grok_summary:
        relevant_code = incident.grok_summary[:500]

    return EvidenceInput(
        error_type=error_type,
        error_message=error_message,
        file="unknown",
        line=0,
        relevant_code=relevant_code,
        stack_trace=stack_trace,
        extra_context={
            "incident_id": incident.incident_id,
            "service": incident.service,
            "container_name": incident.container_name,
            "failure_type": incident.failure_type.value,
            "severity": incident.severity.value,
        },
    )


def _publish_outcome_events(bus: EventBus, outcome: PatchOutcome) -> None:
    """Publish the appropriate sandbox events based on the pipeline outcome."""
    if outcome.validated:
        bus.publish(SANDBOX_VALIDATED, outcome)
        if outcome.git and outcome.git.success:
            bus.publish(SANDBOX_BRANCH_PUSHED, outcome)
        if outcome.pull_request and outcome.pull_request.success:
            bus.publish(SANDBOX_PR_CREATED, outcome)
    elif outcome.error:
        bus.publish(SANDBOX_FAILED, outcome)
    else:
        bus.publish(SANDBOX_REJECTED, outcome)


def _log_outcome(incident_id: str, outcome: PatchOutcome) -> None:
    """Emit a structured log line summarising the pipeline result."""
    if outcome.validated:
        pr_url = outcome.pull_request_url or "(no PR created)"
        logger.info(
            "CodePatchEngine [%s]: ✅ VALIDATED — branch=%s PR=%s",
            incident_id,
            outcome.git.branch_name if outcome.git else "?",
            pr_url,
        )
    else:
        reason = (
            outcome.validation.reason
            if outcome.validation
            else (outcome.error or "unknown reason")
        )
        logger.warning(
            "CodePatchEngine [%s]: ❌ REJECTED — %s",
            incident_id,
            reason,
        )


def _build_pipeline(bus: EventBus) -> SandboxPipeline:
    """Build a SandboxPipeline from the current settings singleton."""
    config = SandboxConfig(
        sandbox_base_dir=settings.sandbox_base_dir,
        docker_timeout_seconds=settings.sandbox_docker_timeout,
        container_startup_timeout=settings.sandbox_container_startup_timeout,
        lint_timeout_seconds=settings.sandbox_lint_timeout,
        test_timeout_seconds=settings.sandbox_test_timeout,
        run_lint=settings.sandbox_run_lint,
        run_tests=settings.sandbox_run_tests,
        run_docker=settings.sandbox_run_docker,
        skip_docker_if_unavailable=settings.sandbox_skip_docker_if_unavailable,
    )
    return SandboxPipeline(
        config=config,
        github_repo=settings.github_repo,
        base_branch=settings.github_base_branch,
        git_username=settings.git_username,
        github_token=settings.github_token,
        bus=bus,
    )
