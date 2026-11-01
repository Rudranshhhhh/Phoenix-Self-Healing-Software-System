"""
Phoenix LLM Engine — Verified fallback fixture tests (STAGE 3)

Tests the canonical severity-count fallback: structural validation against
valid/missing/invalid data, validation against evidence via the existing
_patch validation, and the real isolated-sandbox regression test.

Run:
    python -m pytest agent/ai/llm_engine/test_fallback_patch.py -v
"""
from __future__ import annotations

import pytest

from agent.ai.llm_engine.fallback_patch import (
    EXPECTED_FILES,
    FALLBACK_SOURCE,
    build_fallback_patch,
    load_fallback,
    validate_fallback_data,
    verify_fallback,
)
from agent.ai.llm_engine.run_severity_bug import build_evidence
from agent.ai.llm_engine.patch import FilePatch, PatchResult


SERVICE_FILE = "backend/services/incident_service.py"
REPO_FILE = "backend/repositories/incident_repository.py"


# ============================================================================ #
# Valid fixture                                                                  #
# ============================================================================ #

class TestValidFallback:
    def test_source_is_documented_as_manually_authored(self):
        assert "manually authored" in FALLBACK_SOURCE.lower()
        assert "LLM" in FALLBACK_SOURCE  # explicitly states it is NOT an LLM run

    def test_load_fallback_returns_complete_structure(self):
        data = load_fallback()
        assert isinstance(data, dict)
        assert isinstance(data["patches"], list) and len(data["patches"]) >= 2
        assert "explanation" in data

    def test_build_fallback_patch_is_valid_patchresult(self):
        pr = build_fallback_patch()
        assert isinstance(pr, PatchResult)
        assert pr.is_empty is False
        assert len(pr.patches) >= 2
        files = {p.file for p in pr.patches}
        assert SERVICE_FILE in files
        assert REPO_FILE in files

    def test_validate_fallback_data_accepts_canonical(self):
        ok, reasons = validate_fallback_data(load_fallback())
        assert ok is True
        assert reasons == []

    def test_verify_fallback_against_evidence(self):
        ok, reasons = verify_fallback(build_evidence())
        assert ok is True
        assert reasons == []


# ============================================================================ #
# Missing data                                                                   #
# ============================================================================ #

class TestMissingFallbackData:
    def test_none_rejected(self):
        ok, reasons = validate_fallback_data(None)
        assert ok is False
        assert reasons

    def test_empty_dict_rejected(self):
        ok, reasons = validate_fallback_data({})
        assert ok is False
        assert "patches" in " ".join(reasons)

    def test_empty_patches_list_rejected(self):
        ok, reasons = validate_fallback_data({"patches": [], "explanation": "x"})
        assert ok is False
        assert reasons


# ============================================================================ #
# Invalid data                                                                   #
# ============================================================================ #

class TestInvalidFallbackData:
    def test_missing_required_field_rejected(self):
        ok, reasons = validate_fallback_data({
            "patches": [
                {"file": SERVICE_FILE, "old_code": "", "new_code": "x"}
            ]
        })
        assert ok is False
        assert any("old_code" in r for r in reasons)

    def test_wrong_file_rejected(self):
        ok, reasons = validate_fallback_data({
            "patches": [
                {"file": "backend/other.py", "old_code": "a", "new_code": "b"}
            ]
        })
        assert ok is False
        # wrong file AND no service/repo patch
        assert any("not an expected file" in r for r in reasons)

    def test_only_one_file_rejected_as_incomplete(self):
        # Only service file present -> missing repo -> incomplete.
        ok, reasons = validate_fallback_data({
            "patches": [
                {"file": SERVICE_FILE, "old_code": "a", "new_code": "b"}
            ]
        })
        assert ok is False
        assert any("repositories" in r for r in reasons)

    def test_non_dict_entry_rejected(self):
        ok, reasons = validate_fallback_data({"patches": ["not a dict"]})
        assert ok is False
        assert any("not a dict" in r for r in reasons)


# ============================================================================ #
# Real sandbox regression — the canonical fix must make the test pass            #
# ============================================================================ #

class TestFallbackRegression:
    def test_fallback_passes_regression_in_sandbox(self):
        """Apply the canonical fallback to an isolated backend copy and run the
        regression test. This is the ground-truth check that the fallback is
        actually a correct, complete fix. (Uses a subprocess; ~1-2s.)"""
        from agent.ai.llm_engine.eval_severity_bug import verify_patches_in_sandbox
        pr = build_fallback_patch()
        passed, detail = verify_patches_in_sandbox(list(pr.patches))
        assert passed is True, f"fallback did not pass regression: {detail[-400:]}"
