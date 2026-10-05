"""
Phoenix LLM Engine — Patch Model + Generator (MULTI-FILE)

Defines:
  FilePatch        — a single-file code replacement (file, old_code, new_code).
  PatchResult      — one or more FilePatch objects + a shared explanation.
  generate_patch() — calls the LLM with evidence + diagnosis and parses the fix.

The patch is a PROPOSAL only. This module never writes to disk or modifies
any source file. Applying and validating the patch is the responsibility of
the downstream Sandbox / Validation component.

Why multi-file
--------------
Some real bugs require coordinated changes across more than one file (for
example: pass a new argument at a call site AND add the parameter to the
receiving function). A single old_code/new_code pair cannot represent that,
so PatchResult now holds a list of FilePatch objects.

Validation rules applied after the LLM responds
------------------------------------------------
For EVERY FilePatch:
1. file, old_code, and new_code must be present and non-empty.
2. old_code must be a non-empty string (after stripping whitespace).
3. new_code must be a non-empty string (after stripping whitespace).
4. old_code must exist as a substring of the relevant source code, scoped to
   the file the patch targets. When the evidence's relevant_code contains
   multiple files marked with `# FILE: <path>` headers, old_code is checked
   against THAT file's block only (not the whole blob). If the targeted file
   is not present in the evidence, or old_code is not found in that file's
   block, the patch is rejected.

At the PatchResult level:
- The response must contain a non-empty `patches` list.
- If ANY FilePatch is invalid, the whole PatchResult is rejected (returns None).
  A partial multi-file fix is treated as incomplete and unsafe to apply.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.diagnosis import DiagnosisResult, EvidenceInput
from agent.ai.llm_engine.prompts import SYSTEM_PROMPT, build_patch_prompt

logger = logging.getLogger(__name__)


# ============================================================================ #
# Output Models                                                                  #
# ============================================================================ #

class FilePatch(BaseModel):
    """
    A single-file code replacement proposed by the LLM.

    Fields
    ------
    file        Relative path to the file that needs to change.
    old_code    The exact lines to replace (verbatim, same indentation).
    new_code    The replacement lines (same indentation as old_code).
    """

    # min_length=1 rejects both missing keys and empty strings at construction.
    file: str = Field(min_length=1, description="Relative path to the file to change.")
    old_code: str = Field(min_length=1, description="Exact code to replace (verbatim).")
    new_code: str = Field(min_length=1, description="Replacement code (same indentation).")


class PatchResult(BaseModel):
    """
    A proposed fix: one or more FilePatch objects plus a shared explanation.

    This is a read-only data object. The patch MUST NOT be applied directly
    to the production source tree. It is passed to the Sandbox component for
    isolated testing and validation first.

    Fields
    ------
    patches      One FilePatch per file that must change (>= 1 when generated).
    explanation  One sentence describing what the fix does and why.
    is_empty     True when there are no real patches. Downstream components
                 should treat this as a signal to escalate rather than apply.
    """

    patches: list[FilePatch] = Field(
        default_factory=list,
        description="One FilePatch per file that needs to change.",
    )
    explanation: str = Field(
        default="",
        description="One sentence explaining what the fix does and why it works.",
    )

    # Derived — set automatically
    is_empty: bool = Field(
        default=False,
        description="True when there are no real patches.",
        exclude=True,  # Not serialised into the output JSON
    )

    @model_validator(mode="after")
    def _mark_empty(self) -> "PatchResult":
        """Mark the patch as empty if there are no patches (or all are blank)."""
        empty = len(self.patches) == 0 or all(
            (not p.old_code.strip()) and (not p.new_code.strip()) for p in self.patches
        )
        object.__setattr__(self, "is_empty", empty)
        return self


# ============================================================================ #
# Internal helpers                                                               #
# ============================================================================ #

def _extract_json(raw: str) -> dict:
    """
    Extract the first JSON object from a raw LLM response string.

    Handles models that wrap JSON in markdown fences despite instructions.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {raw!r}")

    return json.loads(cleaned[start:end])


def _norm_path(path: str) -> str:
    """Normalise a file path for comparison (trim + forward slashes)."""
    return path.strip().replace("\\", "/")


def _split_relevant_code(relevant_code: str) -> dict[str, str]:
    """
    Split a (possibly multi-file) relevant_code block into {file_path: source}.

    Recognises `# FILE: <path>` marker lines as produced by the evidence
    builders. The path is the first whitespace-delimited token after the
    marker; the rest of that marker line (e.g. "(function: ...)" notes) is
    ignored. All lines until the next marker form that file's source block.

    Returns an empty dict if NO marker is present (legacy single-file
    evidence). Callers should then validate against the whole block.
    """
    blocks: dict[str, str] = {}
    current_file: Optional[str] = None
    current_lines: list[str] = []
    found_marker = False

    for line in relevant_code.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("# FILE:"):
            found_marker = True
            if current_file is not None:
                blocks[_norm_path(current_file)] = "".join(current_lines)
            rest = stripped[len("# FILE:"):].strip()
            current_file = rest.split()[0] if rest else None
            current_lines = []
        else:
            current_lines.append(line)

    if current_file is not None:
        blocks[_norm_path(current_file)] = "".join(current_lines)

    return blocks if found_marker else {}


# ============================================================================ #
# Patch validation (per FilePatch)                                               #
# ============================================================================ #

def _validate_patch(patch: FilePatch, evidence: EvidenceInput) -> Optional[str]:
    """
    Validate one FilePatch against the evidence.

    Returns None when the patch is valid.
    Returns a human-readable rejection reason string when invalid.

    Rules
    -----
    1. file, old_code, new_code must each be non-empty (after stripping).
    2. old_code must appear as a substring of the relevant source code, scoped
       to the file this patch targets:
         - If relevant_code has `# FILE:` markers, old_code is checked against
           THIS file's block only. If the file is absent from the markers, or
           old_code is not in that file's block, the patch is rejected.
         - If relevant_code has no markers (legacy single-file evidence),
           old_code is checked against the whole relevant_code (old behaviour).
    """
    if not patch.file.strip():
        return f"file is empty — patch rejected"

    if not patch.old_code.strip():
        return f"old_code is empty in {patch.file!r} — patch rejected"

    if not patch.new_code.strip():
        return f"new_code is empty in {patch.file!r} — patch rejected"

    relevant = (evidence.relevant_code or "").strip()
    if not relevant:
        # No relevant_code was provided; skip the substring check.
        logger.debug(
            "LLMEngine/patch: skipping old_code substring check — "
            "no relevant_code in evidence"
        )
        return None

    blocks = _split_relevant_code(relevant)
    if not blocks:
        # Legacy single-file evidence: check against the whole block.
        if patch.old_code.strip() not in relevant:
            return (
                f"old_code not found in relevant_code — patch rejected. "
                f"old_code={patch.old_code.strip()!r}"
            )
        return None

    # Multi-file evidence: validate against this patch's file block only.
    target = blocks.get(_norm_path(patch.file))
    if target is None:
        return (
            f"old_code not found: file {patch.file!r} is not present in "
            f"relevant_code markers — patch rejected"
        )
    if patch.old_code.strip() not in target.strip():
        return (
            f"old_code not found in source for {patch.file!r} — patch rejected. "
            f"old_code={patch.old_code.strip()!r}"
        )
    return None  # valid


# ============================================================================ #
# Generator                                                                      #
# ============================================================================ #

def generate_patch(
    evidence: EvidenceInput,
    diagnosis: DiagnosisResult,
    client: GroqLLMClient,
) -> Optional[PatchResult]:
    """
    Ask the LLM to propose a minimal code fix given the evidence and diagnosis.

    Asks Groq to return one or more file patches. Returns a validated
    PatchResult. Returns None if the LLM call fails, the JSON is malformed,
    the patch list is empty, any patch is missing required fields, or any
    patch fails validation. A partial multi-file fix is rejected in full.

    Args:
        evidence:  The original structured failure evidence.
        diagnosis: The root-cause diagnosis already produced by generate_diagnosis().
        client:    Configured GroqLLMClient instance.

    Returns:
        PatchResult on success (check .is_empty for whether a fix was found),
        None if the LLM call or parsing/validation fails.
    """
    logger.info(
        "LLMEngine/patch: requesting patch for %s in %s:%d",
        evidence.error_type,
        evidence.file,
        evidence.line,
    )

    prompt = build_patch_prompt(evidence, diagnosis)

    raw = client.complete(
        user_prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=1200,  # multi-file patches need more room than single-file did
        temperature=0.1,  # Lower temperature for deterministic code output
    )

    if not raw:
        logger.error("LLMEngine/patch: LLM returned empty response")
        return None

    # --- Parse the JSON envelope ---------------------------------------- #
    try:
        data = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("LLMEngine/patch: JSON parse error — %s\nRaw response: %s", exc, raw)
        return None

    # --- Validate the multi-file structure ------------------------------ #
    patches_data = data.get("patches")
    if not isinstance(patches_data, list):
        logger.error(
            "LLMEngine/patch: response missing 'patches' list — rejected. "
            "Raw response: %s", raw
        )
        return None
    if len(patches_data) == 0:
        logger.error("LLMEngine/patch: empty patch list — rejected")
        return None

    # --- Build FilePatch objects (rejects missing/empty required fields) - #
    try:
        file_patches = [FilePatch(**p) for p in patches_data]
    except (TypeError, ValueError) as exc:
        # pydantic.ValidationError subclasses ValueError; non-dict entries
        # raise TypeError. Either way the response is malformed.
        logger.error("LLMEngine/patch: invalid patch entry — %s", exc)
        return None

    explanation = data.get("explanation") or ""
    result = PatchResult(patches=file_patches, explanation=explanation)

    # --- Validate every patch; reject the whole result if any is invalid - #
    for fp in result.patches:
        reason = _validate_patch(fp, evidence)
        if reason:
            logger.error("LLMEngine/patch: %s", reason)
            return None

    if result.is_empty:
        logger.warning(
            "LLMEngine/patch: LLM could not produce a patch — %s",
            result.explanation or "no explanation given",
        )
    else:
        files = ", ".join(fp.file for fp in result.patches)
        logger.info(
            "LLMEngine/patch: %d patch(es) validated (%s)",
            len(result.patches),
            files,
        )

    return result
