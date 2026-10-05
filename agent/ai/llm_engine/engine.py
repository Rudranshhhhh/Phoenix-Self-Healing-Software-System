"""
Phoenix LLM Engine — Main Entry Point

LLMEngine is the single public interface that downstream Phoenix components
(Sandbox, Validation, Dashboard) interact with.

Pipeline (per call to run()):
  1. Validate evidence with Pydantic → EvidenceInput
  2. Call Grok for root-cause diagnosis → DiagnosisResult
  3. Call Grok for code patch proposal  → PatchResult
  4. Assemble and return LLMEngineResult

Design principles:
  - Never modifies source files.
  - Never triggers Docker, tests, or recovery actions.
  - Degrades gracefully: if diagnosis fails, patch step is skipped.
  - All results are Pydantic-validated.
  - The LLMEngine can be constructed with a pre-built GroqLLMClient
    (for dependency injection in tests) or builds one automatically
    from the environment.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.diagnosis import DiagnosisResult, EvidenceInput, generate_diagnosis
from agent.ai.llm_engine.patch import PatchResult, generate_patch

logger = logging.getLogger(__name__)


# ============================================================================ #
# Output Model                                                                   #
# ============================================================================ #

class LLMEngineResult(BaseModel):
    """
    The complete output of a single LLMEngine.run() call.

    This is the contract between the LLM Engine and all downstream components.

    Fields
    ------
    evidence     The validated input evidence (echoed back for traceability).
    diagnosis    Root-cause analysis. None if the LLM call failed.
    patch        Proposed code fix. None if diagnosis failed or patch call failed.
    success      True when both diagnosis and patch are present and non-empty.
    error        Human-readable reason when success is False.
    ran_at       UTC timestamp of when run() was called.
    """

    evidence: EvidenceInput
    diagnosis: Optional[DiagnosisResult] = None
    patch: Optional[PatchResult] = None
    success: bool = False
    error: Optional[str] = None
    ran_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def summary(self) -> str:
        """Return a one-paragraph human-readable summary for logging/display."""
        if not self.success:
            return (
                f"LLMEngine failed for {self.evidence.error_type} "
                f"in {self.evidence.file}:{self.evidence.line} — {self.error}"
            )
        assert self.diagnosis is not None
        assert self.patch is not None

        patch_status = (
            "no patch generated"
            if (self.patch.is_empty or not self.patch.patches)
            else (
                f"{len(self.patch.patches)} patch(es) ready ("
                + ", ".join(p.file for p in self.patch.patches)
                + ")"
            )
        )
        return (
            f"LLMEngine succeeded for {self.evidence.error_type} "
            f"in {self.evidence.file}:{self.evidence.line}.\n"
            f"  Root cause : {self.diagnosis.root_cause}\n"
            f"  Confidence : {self.diagnosis.confidence * 100:.0f}%\n"
            f"  Patch      : {patch_status}"
        )


# ============================================================================ #
# Engine                                                                         #
# ============================================================================ #

class LLMEngine:
    """
    Phoenix LLM Engine — orchestrates diagnosis and patch generation.

    Construct once and call run() for each failure event.

    Usage
    -----
        engine = LLMEngine()
        result = engine.run(evidence_dict_or_EvidenceInput)

    Or with dependency injection (e.g. in tests):
        client = GroqLLMClient(api_key="test-key", model="llama-3.3-70b-versatile")
        engine = LLMEngine(client=client)
    """

    def __init__(self, client: Optional[GroqLLMClient] = None) -> None:
        """
        Args:
            client: Pre-configured GroqLLMClient. If None, one is constructed
                    automatically from the GROQ_API_KEY environment variable.
        """
        self._client = client or GroqLLMClient()
        logger.info(
            "LLMEngine: initialised (model=%s)",
            self._client.model,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run(self, evidence: EvidenceInput | dict) -> LLMEngineResult:
        """
        Run the full diagnosis + patch pipeline for one failure event.

        Args:
            evidence: Either an EvidenceInput instance or a plain dict that
                      conforms to the EvidenceInput schema.

        Returns:
            LLMEngineResult — always returned, never raises.
            Check .success to determine whether both steps succeeded.
        """
        # Normalise input
        if isinstance(evidence, dict):
            try:
                evidence = EvidenceInput(**evidence)
            except Exception as exc:
                logger.error("LLMEngine: invalid evidence input — %s", exc)
                # Build a minimal fallback to include in the result
                fallback = EvidenceInput(
                    error_type="Unknown",
                    error_message=str(exc),
                )
                return LLMEngineResult(
                    evidence=fallback,
                    success=False,
                    error=f"Evidence validation failed: {exc}",
                )

        logger.info(
            "LLMEngine: starting pipeline for %s in %s:%d",
            evidence.error_type,
            evidence.file,
            evidence.line,
        )

        # ------------------------------------------------------------------ #
        # Step 1 — Diagnosis                                                   #
        # ------------------------------------------------------------------ #
        diagnosis = generate_diagnosis(evidence, self._client)

        if diagnosis is None:
            logger.error(
                "LLMEngine: diagnosis failed for %s in %s:%d — aborting patch step",
                evidence.error_type,
                evidence.file,
                evidence.line,
            )
            return LLMEngineResult(
                evidence=evidence,
                diagnosis=None,
                patch=None,
                success=False,
                error="Diagnosis step failed — LLM returned no response or unparseable JSON.",
            )

        # ------------------------------------------------------------------ #
        # Step 2 — Patch                                                       #
        # ------------------------------------------------------------------ #
        patch = generate_patch(evidence, diagnosis, self._client)

        if patch is None:
            logger.error(
                "LLMEngine: patch generation failed for %s in %s:%d",
                evidence.error_type,
                evidence.file,
                evidence.line,
            )
            return LLMEngineResult(
                evidence=evidence,
                diagnosis=diagnosis,
                patch=None,
                success=False,
                error="Patch step failed — LLM returned no response or unparseable JSON.",
            )

        # ------------------------------------------------------------------ #
        # Assemble result                                                       #
        # ------------------------------------------------------------------ #
        result = LLMEngineResult(
            evidence=evidence,
            diagnosis=diagnosis,
            patch=patch,
            # success=True even if patch.is_empty — we got a valid LLM response;
            # the downstream component decides what to do with an empty patch.
            success=True,
        )

        logger.info("LLMEngine: pipeline complete\n%s", result.summary())
        return result
