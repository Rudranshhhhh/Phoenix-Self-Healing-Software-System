"""
Phoenix LLM Engine — Verified fallback patch fixture (STAGE 3)

A canonical, manually-authored PatchResult for the severity-count demo bug.
It is used by the evaluation harness as a verified fallback when a real Groq
run fails or returns an incomplete patch. It is NEVER applied automatically to
production; the existing safety controls (patch validation + the isolated
sandbox regression test) still gate any use.

Provenance
----------
This fallback was MANUALLY AUTHORED, not produced by an LLM run. It is the
complete two-file fix for the severity-count bug and is verified against the
regression test backend/tests/test_incident_severity_count.py on the
feature/llm-engine branch. Because it is not an LLM output, it must NEVER be
counted as a correct LLM generation — only as a fallback.

Public API
----------
  load_fallback()           -> dict          (the raw JSON-shaped fixture, copied)
  build_fallback_patch()    -> PatchResult   (validated Pydantic object)
  validate_fallback_data(data) -> (bool, list[str])  (structural check)
  verify_fallback(evidence) -> (bool, list[str])      (uses existing _validate_patch)
  apply_fallback_safely(...)  -> delegated to the sandbox; see eval harness.
"""
from __future__ import annotations

import copy
import logging
from typing import Optional

from agent.ai.llm_engine.diagnosis import EvidenceInput
from agent.ai.llm_engine.patch import FilePatch, PatchResult, _validate_patch

logger = logging.getLogger(__name__)

# Provenance — honestly documented. Not from an LLM run.
FALLBACK_SOURCE = (
    "manually authored (canonical severity-count fix; verified against "
    "backend/tests/test_incident_severity_count.py on feature/llm-engine). "
    "Not produced by an LLM run."
)

SERVICE_FILE = "backend/services/incident_service.py"
REPO_FILE = "backend/repositories/incident_repository.py"
EXPECTED_FILES = {SERVICE_FILE, REPO_FILE}

# The canonical complete fix: 1 service edit + 2 repo edits (signature + body).
# Each old_code is a verbatim substring of the real production file, so the
# sandbox can apply it with a plain str.replace(old, new, 1).
_FALLBACK_DATA: dict = {
    "patches": [
        {
            "file": SERVICE_FILE,
            "old_code": (
                "total = repo.count_incidents("
                "service=service, status=status, resolved=resolved)"
            ),
            "new_code": (
                "total = repo.count_incidents("
                "service=service, status=status, severity=severity, resolved=resolved)"
            ),
        },
        {
            "file": REPO_FILE,
            "old_code": (
                "def count_incidents(\n"
                "    service: Optional[str] = None,\n"
                "    status: Optional[str] = None,\n"
                "    resolved: Optional[bool] = None,\n"
                ") -> int:"
            ),
            "new_code": (
                "def count_incidents(\n"
                "    service: Optional[str] = None,\n"
                "    status: Optional[str] = None,\n"
                "    severity: Optional[str] = None,\n"
                "    resolved: Optional[bool] = None,\n"
                ") -> int:"
            ),
        },
        {
            "file": REPO_FILE,
            "old_code": (
                "    if status:\n"
                '        query["status"] = status\n'
                "    if resolved is not None:\n"
                '        query["resolved"] = resolved'
            ),
            "new_code": (
                "    if status:\n"
                '        query["status"] = status\n'
                "    if severity:\n"
                '        query["severity"] = severity\n'
                "    if resolved is not None:\n"
                '        query["resolved"] = resolved'
            ),
        },
    ],
    "explanation": (
        "Pass severity to count_incidents in the service layer and accept + "
        "apply it in the repository so the pagination total matches the filter."
    ),
}


# ============================================================================ #
# Loaders                                                                        #
# ============================================================================ #

def load_fallback() -> dict:
    """Return a deep copy of the canonical fallback fixture (safe to mutate)."""
    return copy.deepcopy(_FALLBACK_DATA)


def build_fallback_patch() -> PatchResult:
    """Construct and return the fallback as a validated PatchResult."""
    data = load_fallback()
    file_patches = [FilePatch(**p) for p in data["patches"]]
    return PatchResult(patches=file_patches, explanation=data.get("explanation", ""))


# ============================================================================ #
# Validation                                                                     #
# ============================================================================ #

def validate_fallback_data(data) -> tuple[bool, list[str]]:
    """
    Structural validation of arbitrary fallback data.

    Returns (ok, reasons). ok is True only when:
      - data is a dict with a non-empty "patches" list,
      - every patch has non-empty file/old_code/new_code strings,
      - every patch targets one of the expected files,
      - at least one patch targets the service file AND at least one targets
        the repository file (i.e. the complete two-file fix is present).
    """
    reasons: list[str] = []
    if not isinstance(data, dict):
        return False, ["data must be a dict"]
    patches = data.get("patches")
    if not isinstance(patches, list) or not patches:
        return False, ["data must contain a non-empty 'patches' list"]

    seen_files: set[str] = set()
    for i, p in enumerate(patches):
        if not isinstance(p, dict):
            reasons.append(f"patch[{i}] is not a dict")
            continue
        for key in ("file", "old_code", "new_code"):
            val = p.get(key)
            if not isinstance(val, str) or not val.strip():
                reasons.append(f"patch[{i}].{key} missing or empty")
        file = p.get("file", "")
        if isinstance(file, str) and file.strip():
            norm = file.strip().replace("\\", "/")
            if norm not in EXPECTED_FILES:
                reasons.append(f"patch[{i}].file {file!r} is not an expected file")
            seen_files.add(norm)

    if not seen_files & {SERVICE_FILE}:
        reasons.append("no patch targets backend/services/incident_service.py")
    if not seen_files & {REPO_FILE}:
        reasons.append("no patch targets backend/repositories/incident_repository.py")

    return (len(reasons) == 0, reasons)


def verify_fallback(evidence: EvidenceInput) -> tuple[bool, list[str]]:
    """
    Validate the fallback against evidence using the EXISTING patch validation
    (_validate_patch). Returns (all_valid, reasons). This does NOT apply the
    patch; the isolated sandbox regression test (in the eval harness) is the
    final gate before any use.
    """
    reasons: list[str] = []
    try:
        patch = build_fallback_patch()
    except Exception as exc:
        return False, [f"fallback does not build into a PatchResult: {exc}"]

    for fp in patch.patches:
        reason = _validate_patch(fp, evidence)
        if reason:
            reasons.append(f"{fp.file}: {reason}")
    return (len(reasons) == 0, reasons)
