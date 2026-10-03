"""
Phoenix LLM Engine — Debugging Prompts

Stores all prompt templates for the LLM Engine.
Kept separate from application logic so prompts can be tuned independently.

Two prompt builders are provided:
  - build_diagnosis_prompt(evidence)  → asks Grok to identify the root cause
  - build_patch_prompt(evidence, diagnosis) → asks Grok to propose a code fix

Both return plain strings. The system prompt instructs Grok to respond
with strict JSON so the output can be parsed deterministically by Pydantic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid circular import — EvidenceInput is defined in diagnosis.py
    # At runtime we only use it as a typed dict, so this is import-free.
    from agent.ai.llm_engine.diagnosis import EvidenceInput, DiagnosisResult

# ============================================================================ #
# System Prompt                                                                  #
# ============================================================================ #

SYSTEM_PROMPT = """\
You are Phoenix's AI Debugging Engine — an expert Python software engineer \
and code debugger working inside an automated self-healing system.

Your job is to analyse evidence about a runtime failure in a Python application \
and return a structured JSON response.

Rules you MUST follow:
1. ALWAYS respond with valid JSON only. No markdown, no prose, no code fences.
2. Do not guess if the evidence is insufficient — state that clearly inside the JSON.
3. Be concise. Developers will read your output on a dashboard.
4. Only suggest changes to files whose source code is present in the provided \
   evidence. Do not invent changes to files not shown.
5. Propose the COMPLETE fix — not merely the first local change that makes the \
   assertion pass. A fix that causes a downstream TypeError or signature \
   mismatch is not a complete fix.
6. Each patch entry must be a drop-in replacement for its old_code snippet — \
   same indentation, same surrounding context.
"""

# ============================================================================ #
# Diagnosis Prompt                                                               #
# ============================================================================ #

_DIAGNOSIS_TEMPLATE = """\
A Python application has encountered the following runtime error.
Analyse the evidence and return a JSON object describing the root cause.

--- EVIDENCE ---
Error Type    : {error_type}
Error Message : {error_message}
File          : {file}
Line          : {line}
Relevant Code : {relevant_code}
Stack Trace   :
{stack_trace}
{extra_context_section}
--- TASK ---
Return a JSON object with EXACTLY this structure (no extra keys):

{{
  "root_cause": "<one sentence: what fundamentally caused the error>",
  "explanation": "<two to four sentences: explain what the code is doing wrong \
and why the error is thrown>",
  "affected_file": "<the file path where the fix should be applied>",
  "affected_line": <integer line number where the fault originates>,
  "confidence": <float between 0.0 and 1.0 representing your confidence>
}}
"""


def build_diagnosis_prompt(evidence: "EvidenceInput") -> str:
    """
    Build the user-turn prompt for root-cause diagnosis.

    Args:
        evidence: Structured evidence about the failure.

    Returns:
        Formatted prompt string ready to send to the LLM.
    """
    extra = ""
    if evidence.extra_context:
        lines = "\n".join(f"  {k}: {v}" for k, v in evidence.extra_context.items())
        extra = f"\nExtra Context:\n{lines}\n"

    return _DIAGNOSIS_TEMPLATE.format(
        error_type=evidence.error_type,
        error_message=evidence.error_message,
        file=evidence.file,
        line=evidence.line,
        relevant_code=evidence.relevant_code or "(not provided)",
        stack_trace=evidence.stack_trace or "(not provided)",
        extra_context_section=extra,
    )


# ============================================================================ #
# Patch Prompt                                                                   #
# ============================================================================ #

_PATCH_TEMPLATE = """\
A Python application has a confirmed bug. A root-cause diagnosis has already \
been produced. Your job is to generate a minimal code fix.

--- EVIDENCE ---
File          : {file}
Line          : {line}
Relevant Code : {relevant_code}
Error Type    : {error_type}
Error Message : {error_message}

--- DIAGNOSIS ---
Root Cause    : {root_cause}
Explanation   : {explanation}
Affected File : {affected_file}
Affected Line : {affected_line}

--- TASK ---
Return a JSON object with EXACTLY this structure (no extra top-level keys):

{{
  "patches": [
    {{
      "file": "<path to a file that needs to change>",
      "old_code": "<the exact line(s) to replace in that file — copy verbatim \
from the relevant_code above>",
      "new_code": "<the replacement line(s) — same indentation as old_code>"
    }}
  ],
  "explanation": "<one sentence: what the fix does and why it resolves the error>"
}}

Constraints:
- "patches" must be a non-empty array. Include ONE entry per file that must \
change. Some bugs need coordinated edits in several files; include every \
file change the fix requires.
- Each old_code must be a verbatim substring of THAT file's source as shown \
in relevant_code.
- Each new_code must be a drop-in replacement with the same indentation as its \
old_code.
- Generate the COMPLETE fix, not merely the first local change that appears \
to address the assertion. A one-sided fix that causes a downstream TypeError \
or signature mismatch is incomplete and will be rejected.
- When a proposed change modifies a function call — adding, removing, or \
renaming an argument — inspect the provided source for the DEFINITION of that \
function. If the function's signature or body must also change for the call \
site fix to work without error, generate a patch entry for that file too.
- Every patch entry in the list must work together as one coherent fix. \
Before finalising your response, mentally apply ALL patches together and \
verify that no patch introduces an obvious TypeError, NameError, or argument \
mismatch in any file shown in the evidence.
- Only include a patch entry if you can provide exact, verbatim old_code taken \
from the relevant_code above. Do not speculate about files not shown in the \
evidence.
- If the complete fix cannot be expressed with the available evidence, return \
"patches" as an empty array and explain why in the explanation field.
"""


def build_patch_prompt(
    evidence: "EvidenceInput",
    diagnosis: "DiagnosisResult",
) -> str:
    """
    Build the user-turn prompt for patch generation.

    Args:
        evidence:  The original structured evidence.
        diagnosis: The diagnosis result already produced by the LLM.

    Returns:
        Formatted prompt string ready to send to the LLM.
    """
    return _PATCH_TEMPLATE.format(
        file=evidence.file,
        line=evidence.line,
        relevant_code=evidence.relevant_code or "(not provided)",
        error_type=evidence.error_type,
        error_message=evidence.error_message,
        root_cause=diagnosis.root_cause,
        explanation=diagnosis.explanation,
        affected_file=diagnosis.affected_file,
        affected_line=diagnosis.affected_line,
    )
