"""
Phoenix LLM Engine — Evidence Input Model + Diagnosis

Defines:
  EvidenceInput   — Pydantic model for structured incoming evidence.
  DiagnosisResult — Pydantic model for the LLM's root-cause analysis.
  generate_diagnosis() — calls the LLM and parses the response.

The evidence schema is intentionally flexible:
  - All fields except error_type and error_message are optional so the module
    can accept partial evidence while other Phoenix components are being built.
  - extra_context is a free-form dict for any additional facts a collector
    wants to pass in (e.g. service name, environment, recent deploys).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.prompts import SYSTEM_PROMPT, build_diagnosis_prompt

logger = logging.getLogger(__name__)


# ============================================================================ #
# Input Model                                                                    #
# ============================================================================ #

class EvidenceInput(BaseModel):
    """
    Structured evidence about a runtime failure in a monitored Python application.

    Produced by the Evidence Collection component and consumed by the LLM Engine.

    All fields beyond error_type and error_message are optional because evidence
    completeness varies depending on the failure mode and which collectors ran.
    """

    # Required — always present
    error_type: str = Field(
        description="The Python exception class name, e.g. 'TypeError'.",
    )
    error_message: str = Field(
        description="The exception message string.",
    )

    # Strongly recommended — present for most code-level failures
    file: str = Field(
        default="unknown",
        description="Relative path to the source file where the error originated.",
    )
    line: int = Field(
        default=0,
        description="Line number in the file where the error occurred (1-indexed).",
        ge=0,
    )
    relevant_code: Optional[str] = Field(
        default=None,
        description="The source code line(s) near the failure point.",
    )
    stack_trace: Optional[str] = Field(
        default=None,
        description="Full stack trace text captured at the time of the failure.",
    )

    # Optional enrichment
    function_name: Optional[str] = Field(
        default=None,
        description="Name of the function/method where the error occurred.",
    )
    extra_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form additional context from collectors: service name, "
            "environment, recent deploys, request payload, etc."
        ),
    )

    @field_validator("error_type", "error_message")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


# ============================================================================ #
# Output Model                                                                   #
# ============================================================================ #

class DiagnosisResult(BaseModel):
    """
    The LLM's structured root-cause analysis of a code failure.

    Produced by generate_diagnosis() and consumed by:
      - patch.py  (to generate a fix)
      - engine.py (to assemble the final LLMEngineResult)
    """

    root_cause: str = Field(
        description="One sentence naming the fundamental cause of the error.",
    )
    explanation: str = Field(
        description=(
            "Two to four sentences explaining what the code is doing wrong "
            "and why the error is thrown."
        ),
    )
    affected_file: str = Field(
        description="Path to the file where the fix should be applied.",
    )
    affected_line: int = Field(
        description="Line number in the file where the fault originates.",
        ge=0,
    )
    confidence: float = Field(
        default=0.0,
        description="LLM confidence score between 0.0 and 1.0.",
        ge=0.0,
        le=1.0,
    )


# ============================================================================ #
# Generator                                                                      #
# ============================================================================ #

def _extract_json(raw: str) -> dict:
    """
    Extract the first JSON object from a raw LLM response string.

    Handles cases where the model wraps the JSON in markdown code fences
    despite being instructed not to.
    """
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("```", "").strip()

    # Find the first { ... } block
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {raw!r}")

    return json.loads(cleaned[start:end])


def generate_diagnosis(
    evidence: EvidenceInput,
    client: GroqLLMClient,
) -> Optional[DiagnosisResult]:
    """
    Ask the LLM to diagnose the root cause of a code failure.

    Sends the formatted evidence prompt to Groq and parses the JSON response
    into a validated DiagnosisResult. Returns None if the LLM call fails or
    the response cannot be parsed.

    Args:
        evidence: Structured failure evidence.
        client:   Configured GroqLLMClient instance.

    Returns:
        DiagnosisResult on success, None on any failure.
    """
    logger.info(
        "LLMEngine/diagnosis: requesting diagnosis for %s in %s:%d",
        evidence.error_type,
        evidence.file,
        evidence.line,
    )

    prompt = build_diagnosis_prompt(evidence)

    raw = client.complete(
        user_prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=600,
        temperature=0.2,
    )

    if not raw:
        logger.error("LLMEngine/diagnosis: LLM returned empty response")
        return None

    try:
        data = _extract_json(raw)
        result = DiagnosisResult(**data)
        logger.info(
            "LLMEngine/diagnosis: root_cause='%.80s' confidence=%.0f%%",
            result.root_cause,
            result.confidence * 100,
        )
        return result

    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("LLMEngine/diagnosis: JSON parse error — %s\nRaw response: %s", exc, raw)
        return None
    except Exception as exc:
        logger.exception("LLMEngine/diagnosis: unexpected error parsing response — %s", exc)
        return None
