"""
Phoenix LLM Engine — Prompt Templates

Two prompt builders:
  build_diagnosis_prompt(evidence)         → root-cause analysis
  build_patch_prompt(evidence, diagnosis)  → minimal code fix

Both return plain strings. The LLM must reply with strict JSON.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.ai.llm_engine.diagnosis import DiagnosisResult, EvidenceInput

# ============================================================================ #
# System Prompt
# ============================================================================ #

SYSTEM_PROMPT = """\
You are Phoenix's AI Debugging Engine — an expert software engineer and code \
debugger working inside an automated self-healing system.

You analyse evidence about CI or runtime failures in software projects \
(Python, TypeScript, JavaScript, and other languages) and return structured JSON.

Rules you MUST follow:
1. ALWAYS respond with valid JSON only. No markdown, no prose, no code fences.
2. Do not guess if the evidence is insufficient — say so inside the JSON.
3. Be concise. Developers read your output on a dashboard.
4. Only suggest changes to files whose source code appears in the evidence. \
   Do not invent changes to files not shown.
5. Each patch old_code must be a verbatim copy from the provided source — \
   same indentation, same surrounding context.
"""

# ============================================================================ #
# Diagnosis Prompt
# ============================================================================ #

_DIAGNOSIS_TEMPLATE = """\
A software project has the following CI/runtime failure.
Analyse the evidence and return a JSON object describing the root cause.

--- EVIDENCE ---
Error Type    : {error_type}
Error Message : {error_message}
File          : {file}
Line          : {line}
Relevant Code :
{relevant_code}

Stack Trace / Logs :
{stack_trace}
{extra_context_section}
--- TASK ---
Return a JSON object with EXACTLY this structure (no extra keys):

{{
  "root_cause": "<one sentence: what fundamentally caused the error>",
  "explanation": "<two to four sentences explaining the bug>",
  "affected_file": "<relative path of the file to fix>",
  "affected_line": <integer line number where the fault originates>,
  "confidence": <float 0.0–1.0>
}}
"""


def build_diagnosis_prompt(evidence: "EvidenceInput") -> str:
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
        stack_trace=(evidence.stack_trace or "(not provided)")[:2000],
        extra_context_section=extra,
    )


# ============================================================================ #
# Patch Prompt
# ============================================================================ #

_PATCH_TEMPLATE = """\
A software project has a confirmed bug. A root-cause diagnosis is provided.
Your job is to generate a minimal code fix as a JSON object.

--- EVIDENCE ---
File          : {file}
Line          : {line}
Error Type    : {error_type}
Error Message : {error_message}

Source code (copy old_code VERBATIM from this):
{relevant_code}

--- DIAGNOSIS ---
Root Cause    : {root_cause}
Explanation   : {explanation}
Affected File : {affected_file}
Affected Line : {affected_line}

--- TASK ---
Return a JSON object with EXACTLY this structure:

{{
  "patches": [
    {{
      "file": "src/phoenix-bug.ts",
      "old_code": "export const buggyValue: number = \\"hello world\\";",
      "new_code": "export const buggyValue: number = 42;"
    }}
  ],
  "explanation": "Changed the string literal to a number to match the declared type."
}}

STRICT RULES:
- "patches" must be a non-empty JSON array.
- Each "old_code" must be copied VERBATIM (exact characters, exact indentation) \
  from the source code shown above. Do NOT paraphrase or reformat.
- Each "new_code" must use the same indentation as its old_code.
- Only patch files whose full source is shown above.
- If you cannot provide exact verbatim old_code, return an empty patches array \
  and explain why.
- Do not include any text outside the JSON object.
"""


def build_patch_prompt(
    evidence: "EvidenceInput",
    diagnosis: "DiagnosisResult",
) -> str:
    return _PATCH_TEMPLATE.format(
        file=evidence.file,
        line=evidence.line,
        relevant_code=evidence.relevant_code or "(source not available — cannot patch)",
        error_type=evidence.error_type,
        error_message=evidence.error_message,
        root_cause=diagnosis.root_cause,
        explanation=diagnosis.explanation,
        affected_file=diagnosis.affected_file or evidence.file,
        affected_line=diagnosis.affected_line or evidence.line,
    )
