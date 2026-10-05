"""
Phoenix LLM Engine — Patch Validation Tests (MULTI-FILE)

Tests for the multi-file patch pipeline:
  - FilePatch / PatchResult models
  - _split_relevant_code (per-file source blocks from `# FILE:` markers)
  - _validate_patch (file-scoped old_code check)
  - generate_patch (parses {patches:[...], explanation}, rejects bad input)

Runs without any API key or network access. Uses a _FixedResponseClient to
supply pre-built LLM responses so every test is deterministic and offline.

Run with:
    pip install pytest pydantic
    python -m pytest agent/ai/llm_engine/test_patch_validation.py -v
"""
from __future__ import annotations

import json
from typing import Optional

import pytest

from agent.ai.llm_engine.diagnosis import DiagnosisResult, EvidenceInput
from agent.ai.llm_engine.patch import (
    FilePatch,
    PatchResult,
    _split_relevant_code,
    _validate_patch,
    generate_patch,
)


# ============================================================================ #
# Fixtures                                                                       #
# ============================================================================ #

SINGLE_RELEVANT_CODE = "    score = mood_score + mood"

# Multi-file evidence with `# FILE:` markers — mirrors the real severity bug.
SERVICE_FILE = "backend/services/incident_service.py"
REPO_FILE = "backend/repositories/incident_repository.py"
MULTI_RELEVANT_CODE = (
    "# FILE: backend/services/incident_service.py   (function: list_incidents)\n"
    "    total = repo.count_incidents(service=service, status=status, resolved=resolved)\n"
    "\n"
    "# FILE: backend/repositories/incident_repository.py   (function: count_incidents)\n"
    "def count_incidents(\n"
    "    service: Optional[str] = None,\n"
    "    status: Optional[str] = None,\n"
    "    resolved: Optional[bool] = None,\n"
    ") -> int:\n"
    "    query: dict = {}\n"
    "    if service:\n"
    "        query[\"service\"] = service\n"
    "    return mongo.incidents().count_documents(query)\n"
)

SERVICE_OLD = "total = repo.count_incidents(service=service, status=status, resolved=resolved)"
SERVICE_NEW = (
    "total = repo.count_incidents("
    "service=service, status=status, severity=severity, resolved=resolved)"
)
REPO_OLD = (
    "def count_incidents(\n"
    "    service: Optional[str] = None,\n"
    "    status: Optional[str] = None,\n"
    "    resolved: Optional[bool] = None,\n"
    ") -> int:"
)
REPO_NEW = (
    "def count_incidents(\n"
    "    service: Optional[str] = None,\n"
    "    status: Optional[str] = None,\n"
    "    severity: Optional[str] = None,\n"
    "    resolved: Optional[bool] = None,\n"
    ") -> int:"
)


def _make_evidence(relevant_code: Optional[str] = SINGLE_RELEVANT_CODE) -> EvidenceInput:
    return EvidenceInput(
        error_type="TypeError",
        error_message="unsupported operand type(s) for +: 'int' and 'str'",
        file="backend/app/moods.py",
        line=42,
        relevant_code=relevant_code,
    )


def _make_multi_evidence() -> EvidenceInput:
    return EvidenceInput(
        error_type="AssertionError",
        error_message="expected total = 1, actual total = 3",
        file=SERVICE_FILE,
        line=54,
        relevant_code=MULTI_RELEVANT_CODE,
    )


def _make_diagnosis() -> DiagnosisResult:
    return DiagnosisResult(
        root_cause="severity is not passed to count_incidents",
        explanation="The count query ignores the severity filter.",
        affected_file=SERVICE_FILE,
        affected_line=54,
        confidence=0.9,
    )


def _file_patch(
    file: str = "backend/app/moods.py",
    old_code: str = "score = mood_score + mood",
    new_code: str = "score = mood_score + str(mood)",
) -> FilePatch:
    return FilePatch(file=file, old_code=old_code, new_code=new_code)


class _FixedResponseClient:
    """Minimal fake client returning a fixed JSON string for complete()."""

    def __init__(self, response: Optional[str]) -> None:
        self._response = response
        self.model = "test-fixed"

    def complete(self, user_prompt, system_prompt=None, max_tokens=None, temperature=None):
        return self._response


# ============================================================================ #
# Model tests                                                                    #
# ============================================================================ #

class TestPatchResultModel:
    def test_empty_patches_is_marked_empty(self):
        pr = PatchResult(patches=[], explanation="cannot fix")
        assert pr.is_empty is True

    def test_with_patches_is_not_empty(self):
        pr = PatchResult(patches=[_file_patch()], explanation="fix")
        assert pr.is_empty is False
        assert len(pr.patches) == 1

    def test_filepatch_rejects_missing_file(self):
        with pytest.raises(Exception):
            FilePatch(old_code="x", new_code="y")

    def test_filepatch_rejects_empty_old_code(self):
        with pytest.raises(Exception):
            FilePatch(file="a.py", old_code="", new_code="y")

    def test_filepatch_rejects_empty_new_code(self):
        with pytest.raises(Exception):
            FilePatch(file="a.py", old_code="x", new_code="")

    def test_filepatch_rejects_whitespace_only_file(self):
        # min_length=1 allows "   " at construction; _validate_patch catches it.
        fp = FilePatch(file="   ", old_code="x", new_code="y")
        ev = _make_evidence("x")
        assert _validate_patch(fp, ev) is not None  # rejected as empty file


# ============================================================================ #
# _split_relevant_code — per-file block extraction                               #
# ============================================================================ #

class TestSplitRelevantCode:
    def test_no_markers_returns_empty_dict(self):
        assert _split_relevant_code(SINGLE_RELEVANT_CODE) == {}

    def test_multi_file_splits_by_markers(self):
        blocks = _split_relevant_code(MULTI_RELEVANT_CODE)
        assert set(blocks.keys()) == {SERVICE_FILE, REPO_FILE}
        assert "count_incidents" in blocks[SERVICE_FILE]
        assert "def count_incidents" in blocks[REPO_FILE]

    def test_marker_path_is_first_token_after_marker(self):
        # The "(function: ...)" note on the marker line must NOT become part of the path.
        blocks = _split_relevant_code(MULTI_RELEVANT_CODE)
        assert "backend/services/incident_service.py" in blocks
        # ensure the note didn't leak into the path key
        assert all("(function" not in k for k in blocks)


# ============================================================================ #
# _validate_patch — file-scoped validation                                       #
# ============================================================================ #

class TestValidatePatch:
    def test_valid_single_file_patch(self):
        ev = _make_evidence("    score = mood_score + mood")
        fp = _file_patch(old_code="score = mood_score + mood")
        assert _validate_patch(fp, ev) is None

    def test_valid_two_file_patches_each_in_own_block(self):
        ev = _make_multi_evidence()
        p1 = FilePatch(file=SERVICE_FILE, old_code=SERVICE_OLD, new_code=SERVICE_NEW)
        p2 = FilePatch(file=REPO_FILE, old_code=REPO_OLD, new_code=REPO_NEW)
        assert _validate_patch(p1, ev) is None
        assert _validate_patch(p2, ev) is None

    def test_old_code_not_in_relevant_code_rejected(self):
        ev = _make_evidence("    score = mood_score + mood")
        fp = _file_patch(old_code="result = completely_wrong + thing")
        reason = _validate_patch(fp, ev)
        assert reason is not None
        assert "old_code not found in relevant_code" in reason

    def test_old_code_in_wrong_file_block_rejected(self):
        # old_code is the service line, but the patch claims the repo file.
        ev = _make_multi_evidence()
        fp = FilePatch(file=REPO_FILE, old_code=SERVICE_OLD, new_code=SERVICE_NEW)
        reason = _validate_patch(fp, ev)
        assert reason is not None
        assert "not found in source" in reason

    def test_file_not_in_markers_rejected(self):
        ev = _make_multi_evidence()
        fp = FilePatch(file="backend/other.py", old_code=SERVICE_OLD, new_code=SERVICE_NEW)
        reason = _validate_patch(fp, ev)
        assert reason is not None
        assert "not present in relevant_code markers" in reason

    def test_empty_old_code_rejected(self):
        ev = _make_evidence("x")
        # FilePatch min_length forbids "" at construction; craft whitespace-only.
        fp = FilePatch(file="a.py", old_code="   ", new_code="y")
        reason = _validate_patch(fp, ev)
        assert reason is not None
        assert "old_code is empty" in reason

    def test_empty_new_code_rejected(self):
        ev = _make_evidence("x")
        fp = FilePatch(file="a.py", old_code="x", new_code="   ")
        reason = _validate_patch(fp, ev)
        assert reason is not None
        assert "new_code is empty" in reason

    def test_no_relevant_code_skips_substring_check(self):
        ev = _make_evidence(relevant_code=None)
        fp = _file_patch(old_code="anything", new_code="something")
        assert _validate_patch(fp, ev) is None

    def test_legacy_single_file_evidence_no_markers(self):
        # No markers -> validate against the whole relevant_code (backward compat).
        ev = _make_evidence("    score = mood_score + mood")
        fp = _file_patch(old_code="score = mood_score + mood")
        assert _validate_patch(fp, ev) is None


# ============================================================================ #
# generate_patch — integration via fake client                                   #
# ============================================================================ #

class TestGeneratePatch:
    def _resp(self, obj: dict) -> str:
        return json.dumps(obj)

    def test_valid_one_file_patch_returned(self):
        ev = _make_evidence("    score = mood_score + mood")
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"file": "backend/app/moods.py",
                 "old_code": "score = mood_score + mood",
                 "new_code": "score = mood_score + str(mood)"}
            ],
            "explanation": "Convert mood to int.",
        }))
        result = generate_patch(ev, _make_diagnosis(), client)
        assert result is not None
        assert len(result.patches) == 1
        assert result.patches[0].file == "backend/app/moods.py"
        assert "str(mood)" in result.patches[0].new_code
        assert result.explanation == "Convert mood to int."
        assert result.is_empty is False

    def test_valid_two_file_patch_returned(self):
        ev = _make_multi_evidence()
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"file": SERVICE_FILE, "old_code": SERVICE_OLD, "new_code": SERVICE_NEW},
                {"file": REPO_FILE, "old_code": REPO_OLD, "new_code": REPO_NEW},
            ],
            "explanation": "Pass severity to the count and accept it in the repo.",
        }))
        result = generate_patch(ev, _make_diagnosis(), client)
        assert result is not None
        assert len(result.patches) == 2
        assert result.patches[0].file == SERVICE_FILE
        assert result.patches[1].file == REPO_FILE
        assert "severity=severity" in result.patches[0].new_code
        assert "severity: Optional[str]" in result.patches[1].new_code
        assert result.is_empty is False

    def test_empty_patch_list_rejected(self):
        ev = _make_evidence()
        client = _FixedResponseClient(self._resp({"patches": [], "explanation": "no fix"}))
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_malformed_json_rejected(self):
        ev = _make_evidence()
        client = _FixedResponseClient("this is not json at all")
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_missing_patches_key_rejected(self):
        # Old single-file shape is no longer accepted.
        ev = _make_evidence("    score = mood_score + mood")
        client = _FixedResponseClient(self._resp({
            "file": "backend/app/moods.py",
            "old_code": "score = mood_score + mood",
            "new_code": "score = mood_score + str(mood)",
            "explanation": "old format",
        }))
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_missing_required_field_in_patch_rejected(self):
        ev = _make_evidence("    score = mood_score + mood")
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"old_code": "score = mood_score + mood",
                 "new_code": "score = mood_score + str(mood)"}
                # missing "file"
            ],
            "explanation": "x",
        }))
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_one_valid_one_invalid_rejected(self):
        # A partial multi-file fix must be rejected in full.
        ev = _make_multi_evidence()
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"file": SERVICE_FILE, "old_code": SERVICE_OLD, "new_code": SERVICE_NEW},
                {"file": REPO_FILE, "old_code": "def totally_wrong():", "new_code": "pass"},
            ],
            "explanation": "partial",
        }))
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_old_code_not_present_rejected(self):
        ev = _make_evidence("    score = mood_score + mood")
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"file": "backend/app/moods.py",
                 "old_code": "result = foo + bar",
                 "new_code": "result = int(foo) + bar"}
            ],
            "explanation": "x",
        }))
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_llm_returns_none_propagates(self):
        ev = _make_evidence()
        client = _FixedResponseClient(None)
        assert generate_patch(ev, _make_diagnosis(), client) is None

    def test_extra_keys_in_patch_entry_ignored(self):
        ev = _make_evidence("    score = mood_score + mood")
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"file": "backend/app/moods.py",
                 "old_code": "score = mood_score + mood",
                 "new_code": "score = mood_score + str(mood)",
                 "explanation": "per-patch should be ignored"}
            ],
            "explanation": "top-level explanation wins",
        }))
        result = generate_patch(ev, _make_diagnosis(), client)
        assert result is not None
        assert result.explanation == "top-level explanation wins"

    def test_patch_result_dumps_to_patches_and_explanation(self):
        ev = _make_evidence("    score = mood_score + mood")
        client = _FixedResponseClient(self._resp({
            "patches": [
                {"file": "backend/app/moods.py",
                 "old_code": "score = mood_score + mood",
                 "new_code": "score = mood_score + str(mood)"}
            ],
            "explanation": "fix",
        }))
        result = generate_patch(ev, _make_diagnosis(), client)
        assert result is not None
        dumped = result.model_dump(exclude={"is_empty"})
        assert "patches" in dumped
        assert "explanation" in dumped
        # old single-file keys must not leak into the dump
        assert "file" not in dumped
        assert "old_code" not in dumped
