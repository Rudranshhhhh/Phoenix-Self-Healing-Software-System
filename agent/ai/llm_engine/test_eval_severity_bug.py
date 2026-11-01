"""
Phoenix LLM Engine — Evaluation harness tests (STAGE 4)

Deterministic tests for eval_severity_bug.evaluate() using a scripted client
(returns canned diagnosis/patch JSON) and a mocked sandbox verifier (no
subprocess, no real API key, no network).

Run:
    python -m pytest agent/ai/llm_engine/test_eval_severity_bug.py -v
"""
from __future__ import annotations

import json
from collections import deque
from typing import Optional

import pytest

from agent.ai.llm_engine.eval_severity_bug import evaluate
from agent.ai.llm_engine.fallback_patch import build_fallback_patch, load_fallback
from agent.ai.llm_engine.run_severity_bug import build_evidence
from agent.ai.llm_engine.patch import FilePatch

SERVICE_FILE = "backend/services/incident_service.py"
REPO_FILE = "backend/repositories/incident_repository.py"


# ============================================================================ #
# Scripted client + canned responses                                            #
# ============================================================================ #

def _diag_json() -> str:
    return json.dumps({
        "root_cause": "severity missing from count_incidents call",
        "explanation": "The count query ignores the severity filter.",
        "affected_file": SERVICE_FILE,
        "affected_line": 54,
        "confidence": 0.9,
    })


def _complete_patch_json() -> str:
    # The canonical complete fix (reuses the verified fallback fixture).
    return json.dumps(load_fallback())


def _service_only_patch_json() -> str:
    # A one-file patch that passes the engine's own validation but is incomplete.
    return json.dumps({
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
            }
        ],
        "explanation": "service only — incomplete",
    })


class _ScriptedClient:
    """Returns pre-built responses in order, popping from a queue."""

    def __init__(self, responses):
        self._q = deque(responses)
        self.model = "scripted"

    def complete(self, **kwargs) -> Optional[str]:
        return self._q.popleft() if self._q else None


def _sandbox_both_files(patches: list[FilePatch]) -> tuple[bool, str]:
    """Mocked sandbox: CORRECT iff the patch set touches BOTH expected files."""
    files = {p.file for p in patches}
    return (SERVICE_FILE in files and REPO_FILE in files, "ok" if len(files) == 2 else "incomplete")


def _sandbox_always_pass(patches: list[FilePatch]) -> tuple[bool, str]:
    return (True, "ok")


# ============================================================================ #
# Tests                                                                         #
# ============================================================================ #

class TestCorrectness:
    def test_correct_two_file_patch_counts_as_correct(self):
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), _complete_patch_json()])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["correct"] == 1
        assert s["incorrect"] == 0
        assert s["api_failures"] == 0
        assert s["max_streak"] == 1
        assert s["current_streak"] == 1
        assert s["records"][0]["outcome"] == "CORRECT"
        assert s["records"][0]["sandbox_passed"] is True

    def test_service_only_patch_counts_as_incorrect(self):
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), _service_only_patch_json()])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["correct"] == 0
        assert s["incorrect"] == 1
        assert s["api_failures"] == 0
        assert s["max_streak"] == 0
        assert s["current_streak"] == 0
        assert s["records"][0]["outcome"] == "INCORRECT"
        assert s["records"][0]["sandbox_passed"] is False

    def test_api_failure_counted_not_correct(self):
        # Diagnosis call returns None -> engine aborts -> API_FAILURE.
        ev = build_evidence()
        client = _ScriptedClient([None])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["correct"] == 0
        assert s["api_failures"] == 1
        assert s["max_streak"] == 0
        assert s["records"][0]["outcome"] == "API_FAILURE"

    def test_patch_none_counts_as_api_failure(self):
        # Diagnosis succeeds but patch call returns None -> API_FAILURE.
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), None])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["api_failures"] == 1
        assert s["correct"] == 0


class TestStreakTracking:
    def test_three_correct_then_incorrect_then_correct(self):
        ev = build_evidence()
        responses = (
            [_diag_json(), _complete_patch_json()] * 3
            + [_diag_json(), _service_only_patch_json()]
            + [_diag_json(), _complete_patch_json()]
        )
        client = _ScriptedClient(responses)
        s = evaluate(client, ev, runs=5, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["correct"] == 4
        assert s["incorrect"] == 1
        assert s["api_failures"] == 0
        assert s["current_streak"] == 1          # last run was correct
        assert s["max_streak"] == 3              # the first three in a row
        outcomes = [r["outcome"] for r in s["records"]]
        assert outcomes == ["CORRECT", "CORRECT", "CORRECT", "INCORRECT", "CORRECT"]

    def test_streak_resets_on_api_failure(self):
        ev = build_evidence()
        responses = (
            [_diag_json(), _complete_patch_json()] * 2
            + [None]                              # api failure
            + [_diag_json(), _complete_patch_json()]
        )
        client = _ScriptedClient(responses)
        s = evaluate(client, ev, runs=4, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["correct"] == 3
        assert s["api_failures"] == 1
        assert s["current_streak"] == 1
        assert s["max_streak"] == 2


class TestMockAndFallback:
    def test_mock_mode_is_labelled_not_counted_as_real(self):
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), _complete_patch_json()])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="mock")
        assert s["mode"] == "mock"
        assert s["records"][0]["mode"] == "mock"
        # The summary records the mode so a caller can separate mock from real.
        assert s["correct"] == 1            # counted only within this mock-mode call
        assert s["real_correct"] == 0       # mock success is NEVER counted as real
        assert s["mock_correct"] == 1

    def test_fallback_used_not_counted_as_llm_success(self):
        ev = build_evidence()
        # API failure (diagnosis None) -> fallback should be used and verified.
        client = _ScriptedClient([None])
        fallback = build_fallback_patch()
        s = evaluate(
            client, ev, runs=1, sandbox_verify=_sandbox_always_pass,
            use_fallback=True, fallback=fallback, mode="real",
        )
        assert s["correct"] == 0                    # fallback NOT counted as LLM success
        assert s["api_failures"] == 1
        assert s["fallback_used"] == 1
        assert s["fallback_verified"] == 1
        assert s["max_streak"] == 0                  # API failure resets streak
        rec = s["records"][0]
        assert rec["outcome"] == "API_FAILURE"
        assert rec["used_fallback"] is True
        assert rec["fallback_verified"] is True

    def test_no_fallback_when_disabled(self):
        ev = build_evidence()
        client = _ScriptedClient([None])
        s = evaluate(
            client, ev, runs=1, sandbox_verify=_sandbox_always_pass,
            use_fallback=False, fallback=None, mode="real",
        )
        assert s["fallback_used"] == 0
        assert s["correct"] == 0
        assert s["api_failures"] == 1


class TestRecordsShape:
    def test_files_touched_recorded_for_success(self):
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), _complete_patch_json()])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        files = s["records"][0]["files_touched"]
        assert SERVICE_FILE in files
        assert REPO_FILE in files
        assert s["records"][0]["patch_count"] == 3

    def test_harness_continues_after_exception(self):
        ev = build_evidence()
        # A client that raises on the first call, then succeeds.
        class _BoomThenOk:
            def __init__(self):
                self.calls = 0
                self.model = "boom"
            def complete(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("transient boom")
                return _diag_json() if self.calls == 2 else _complete_patch_json()
        client = _BoomThenOk()
        s = evaluate(client, ev, runs=2, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["records"][0]["outcome"] == "HARNESS_ERROR"
        assert s["records"][1]["outcome"] == "CORRECT"


class TestFailureCategorization:
    """API errors (no response) must be distinguished from patch-generation /
    validation failures (a response came back but was bad)."""

    def test_api_failure_diagnosis_none(self):
        ev = build_evidence()
        client = _ScriptedClient([None])  # diagnosis call: no response
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["api_failures"] == 1
        assert s["diagnosis_failures"] == 0
        assert s["patch_failures"] == 0
        assert s["records"][0]["outcome"] == "API_FAILURE"

    def test_api_failure_patch_none(self):
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), None])  # patch call: no response
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["api_failures"] == 1
        assert s["patch_failures"] == 0
        assert s["records"][0]["outcome"] == "API_FAILURE"

    def test_diagnosis_parse_failure(self):
        ev = build_evidence()
        client = _ScriptedClient(["not json"])  # diagnosis returned content, unparseable
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["diagnosis_failures"] == 1
        assert s["api_failures"] == 0
        assert s["patch_failures"] == 0
        assert s["records"][0]["outcome"] == "DIAGNOSIS_FAILURE"

    def test_patch_malformed_is_patch_failure(self):
        ev = build_evidence()
        client = _ScriptedClient([_diag_json(), "not json"])  # patch content unparseable
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["patch_failures"] == 1
        assert s["api_failures"] == 0
        assert s["diagnosis_failures"] == 0
        assert s["records"][0]["outcome"] == "PATCH_FAILURE"

    def test_patch_validation_rejected_is_patch_failure(self):
        # Patch JSON is well-formed but old_code is not in the source -> the
        # engine's _validate_patch rejects it. This is a validation failure,
        # NOT an API failure.
        ev = build_evidence()
        bad_patch = json.dumps({
            "patches": [
                {
                    "file": SERVICE_FILE,
                    "old_code": "THIS STRING IS NOT IN THE SOURCE",
                    "new_code": "x = 1",
                }
            ],
            "explanation": "bad",
        })
        client = _ScriptedClient([_diag_json(), bad_patch])
        s = evaluate(client, ev, runs=1, sandbox_verify=_sandbox_both_files, mode="real")
        assert s["patch_failures"] == 1
        assert s["api_failures"] == 0
        assert s["records"][0]["outcome"] == "PATCH_FAILURE"
        assert s["correct"] == 0


class TestMockClientSeverityPatch:
    """The mock must return a realistic, VALID two-file patch for the severity
    bug so the offline harness can exercise its CORRECT path end-to-end."""

    def test_mock_client_patch_passes_engine_validation(self):
        from agent.ai.llm_engine.engine import LLMEngine
        from agent.ai.llm_engine.mock_client import MockLLMClient
        ev = build_evidence()
        engine = LLMEngine(client=MockLLMClient())
        result = engine.run(ev)
        assert result.success is True
        assert result.patch is not None
        files = {fp.file for fp in result.patch.patches}
        assert SERVICE_FILE in files
        assert REPO_FILE in files

    def test_mock_client_patch_passes_regression_in_sandbox(self):
        from agent.ai.llm_engine.eval_severity_bug import verify_patches_in_sandbox
        from agent.ai.llm_engine.mock_client import MockLLMClient
        from agent.ai.llm_engine.engine import LLMEngine
        ev = build_evidence()
        result = LLMEngine(client=MockLLMClient()).run(ev)
        assert result.patch is not None
        passed, detail = verify_patches_in_sandbox(list(result.patch.patches))
        assert passed is True, f"mock patch did not pass regression: {detail[-300:]}"

    def test_mock_results_still_labelled_mock(self):
        # Even though the mock now produces a CORRECT patch, the harness mode
        # flag must remain "mock" and real_correct must stay 0.
        from agent.ai.llm_engine.mock_client import MockLLMClient
        from agent.ai.llm_engine.eval_severity_bug import evaluate, verify_patches_in_sandbox
        ev = build_evidence()
        s = evaluate(MockLLMClient(), ev, runs=1,
                     sandbox_verify=verify_patches_in_sandbox, mode="mock")
        assert s["mode"] == "mock"
        assert s["records"][0]["mode"] == "mock"
        assert s["correct"] == 1            # mock correct
        assert s["real_correct"] == 0       # never counted as real
        assert s["mock_correct"] == 1
