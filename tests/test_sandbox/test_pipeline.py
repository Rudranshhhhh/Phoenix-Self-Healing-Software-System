"""
Phoenix Sandbox Tests — Pipeline Integration

Tests for agent/sandbox/pipeline.py (SandboxPipeline).

These are the core integration tests that verify the complete flow:
  LLM patch → sandbox → validate → branch → PR

All external side-effects are mocked:
  - SandboxWorkspace.create / cleanup (filesystem)
  - apply_patch (patch applicator)
  - validate_sandbox (validator)
  - create_branch_and_commit (git)
  - create_pull_request (github)

No real filesystem copies, no Docker, no Git, no GitHub API calls.
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

from agent.ai.llm_engine.diagnosis import DiagnosisResult, EvidenceInput
from agent.ai.llm_engine.engine import LLMEngineResult
from agent.ai.llm_engine.patch import FilePatch, PatchResult
from agent.sandbox.models import (
    GitResult,
    PatchOutcome,
    PRResult,
    SandboxConfig,
    ValidationResult,
)
from agent.sandbox.patch_applicator import ApplicationResult
from agent.sandbox.pipeline import SandboxPipeline


# ============================================================================ #
# Shared test fixtures                                                           #
# ============================================================================ #

INCIDENT_ID = "INC-007"
REPO_PATH = pathlib.Path("/fake/repo")

EVIDENCE = EvidenceInput(
    error_type="AssertionError",
    error_message="expected total = 1, actual total = 3",
    file="backend/services/incident_service.py",
    line=54,
    relevant_code="total = repo.count_incidents(service=service, resolved=resolved)",
)

DIAGNOSIS = DiagnosisResult(
    root_cause="severity is not passed to count_incidents",
    explanation="The count query ignores the severity filter.",
    affected_file="backend/services/incident_service.py",
    affected_line=54,
    confidence=0.9,
)

GOOD_PATCH = PatchResult(
    patches=[
        FilePatch(
            file="backend/services/incident_service.py",
            old_code="total = repo.count_incidents(service=service, resolved=resolved)",
            new_code="total = repo.count_incidents(service=service, severity=severity, resolved=resolved)",
        )
    ],
    explanation="Pass severity to the count query.",
)

GOOD_LLM_RESULT = LLMEngineResult(
    evidence=EVIDENCE,
    diagnosis=DIAGNOSIS,
    patch=GOOD_PATCH,
    success=True,
)

FAILED_LLM_RESULT = LLMEngineResult(
    evidence=EVIDENCE,
    diagnosis=None,
    patch=None,
    success=False,
    error="Diagnosis step failed.",
)

EMPTY_LLM_RESULT = LLMEngineResult(
    evidence=EVIDENCE,
    diagnosis=DIAGNOSIS,
    patch=PatchResult(patches=[], explanation="no fix"),
    success=True,
)


def _passing_validation() -> ValidationResult:
    v = ValidationResult(incident_id=INCIDENT_ID)
    v.build_passed = True
    v.lint_passed = True
    v.tests_passed = True
    v.container_started = True
    v.original_failure_resolved = True
    v.validated = True
    v.reason = "All validation checks passed."
    return v


def _failing_validation(reason: str = "tests failed") -> ValidationResult:
    v = ValidationResult(incident_id=INCIDENT_ID)
    v.build_passed = True
    v.lint_passed = True
    v.tests_passed = False
    v.container_started = True
    v.original_failure_resolved = False
    v.validated = False
    v.reason = f"Patch rejected — {reason}."
    return v


def _good_git() -> GitResult:
    return GitResult(
        success=True,
        branch_name=f"phoenix/fix/{INCIDENT_ID}",
        commit_sha="abc1234def5678",
        commit_message=f"fix({INCIDENT_ID}): Pass severity to the count query.",
        remote_url="https://github.com/myorg/myrepo",
    )


def _good_pr() -> PRResult:
    return PRResult(
        success=True,
        pr_number=42,
        pr_url=f"https://github.com/myorg/myrepo/pull/42",
        title=f"fix({INCIDENT_ID}): automated Phoenix fix",
        base_branch="main",
        head_branch=f"phoenix/fix/{INCIDENT_ID}",
    )


def _make_pipeline(**kwargs) -> SandboxPipeline:
    cfg = SandboxConfig(run_lint=True, run_tests=True, run_docker=False)
    return SandboxPipeline(
        config=cfg,
        github_repo="myorg/myrepo",
        base_branch="main",
        **kwargs,
    )


# ============================================================================ #
# Test 1 — Valid patch → validation succeeds → branch + PR created             #
# ============================================================================ #

class TestValidPatchFullFlow:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_validated_true(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        pipeline = _make_pipeline()
        outcome = pipeline.run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.validated is True

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_branch_created(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.git is not None
        assert outcome.git.branch_name == f"phoenix/fix/{INCIDENT_ID}"

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_commit_created(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.git.commit_sha == "abc1234def5678"

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_pr_created(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.pull_request is not None
        assert outcome.pull_request.pr_number == 42
        assert outcome.pull_request_url == "https://github.com/myorg/myrepo/pull/42"

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_sandbox_cleaned_up(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        mock_ws, _ = _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        mock_ws.cleanup.assert_called_once()

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_incident_id_in_branch_name(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        for inc_id in ("INC-001", "INC-042", "BUG-99"):
            git = GitResult(
                success=True,
                branch_name=f"phoenix/fix/{inc_id}",
                commit_sha="abc123",
                commit_message="fix",
                remote_url="https://github.com/x/y",
            )
            mock_git.return_value = git
            outcome = _make_pipeline().run(inc_id, REPO_PATH, GOOD_LLM_RESULT)
            assert f"phoenix/fix/{inc_id}" == outcome.git.branch_name


# ============================================================================ #
# Test 2 — Invalid patch → validation fails → no branch/PR                     #
# ============================================================================ #

class TestInvalidPatchRejected:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_validated_false(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     validation=_failing_validation())
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.validated is False

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_no_branch_created(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     validation=_failing_validation())
        _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        mock_git.assert_not_called()

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_no_pr_created(self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     validation=_failing_validation())
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        mock_pr.assert_not_called()
        assert outcome.pull_request is None

    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_sandbox_still_cleaned_up_on_failure(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        mock_ws, _ = _setup_mocks(
            mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
            validation=_failing_validation(),
        )
        _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        mock_ws.cleanup.assert_called_once()


# ============================================================================ #
# Test 3 — Build failure                                                        #
# ============================================================================ #

class TestBuildFailure:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_build_failure_rejected(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        build_fail = _failing_validation("build failed")
        build_fail.build_passed = False
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     validation=build_fail)
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.validated is False
        mock_git.assert_not_called()


# ============================================================================ #
# Test 4 — Test failure                                                         #
# ============================================================================ #

class TestTestFailure:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_test_failure_rejected(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     validation=_failing_validation("tests failed"))
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.validated is False
        assert outcome.git is None


# ============================================================================ #
# Test 5 — Original error still present                                         #
# ============================================================================ #

class TestOriginalErrorStillPresent:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_original_error_still_present_rejected(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        not_fixed = _failing_validation("original failure still present")
        not_fixed.original_failure_resolved = False
        not_fixed.tests_passed = True
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     validation=not_fixed)
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.validated is False
        assert outcome.git is None


# ============================================================================ #
# Test 6 — LLM result failures                                                  #
# ============================================================================ #

class TestLLMResultFailures:
    def test_failed_llm_result_rejected_immediately(self):
        pipeline = _make_pipeline()
        outcome = pipeline.run(INCIDENT_ID, REPO_PATH, FAILED_LLM_RESULT)
        assert outcome.validated is False
        assert "Diagnosis step failed" in (outcome.error or "")

    def test_empty_patch_rejected_immediately(self):
        pipeline = _make_pipeline()
        outcome = pipeline.run(INCIDENT_ID, REPO_PATH, EMPTY_LLM_RESULT)
        assert outcome.validated is False
        assert "empty patch" in (outcome.error or "").lower()


# ============================================================================ #
# Test 7 — Patch application failure                                            #
# ============================================================================ #

class TestPatchApplicationFailure:
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_application_failure_rejected(self, mock_ws_cls, mock_apply, mock_validate):
        mock_ws = MagicMock()
        mock_ws_cls.create.return_value = mock_ws
        mock_apply.return_value = ApplicationResult(
            success=False, error="old_code not found in sandbox"
        )
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        assert outcome.validated is False
        assert "old_code not found" in (outcome.error or "")
        mock_validate.assert_not_called()
        mock_ws.cleanup.assert_called_once()


# ============================================================================ #
# Test 8 — Git failure after validation succeeds                               #
# ============================================================================ #

class TestGitFailureAfterValidation:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_git_failure_returns_partial_outcome(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     git=GitResult(success=False, error="push rejected"))
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        # Validation passed but Git failed
        assert outcome.validated is True
        assert outcome.git is not None
        assert outcome.git.success is False
        assert "push rejected" in (outcome.error or "")
        # PR must not be created
        mock_pr.assert_not_called()


# ============================================================================ #
# Test 9 — PR failure after Git succeeds                                       #
# ============================================================================ #

class TestPRFailureAfterGit:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_pr_failure_does_not_fail_outcome(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr,
                     pr=PRResult(success=False, error="GITHUB_TOKEN not set"))
        outcome = _make_pipeline().run(INCIDENT_ID, REPO_PATH, GOOD_LLM_RESULT)
        # Branch was pushed, even if PR failed
        assert outcome.validated is True
        assert outcome.git.success is True
        assert outcome.pull_request.success is False
        assert outcome.pull_request_url == ""


# ============================================================================ #
# Test 10 — run_patch() direct API                                             #
# ============================================================================ #

class TestRunPatchDirectAPI:
    @patch("agent.sandbox.pipeline.create_pull_request")
    @patch("agent.sandbox.pipeline.create_branch_and_commit")
    @patch("agent.sandbox.pipeline.validate_sandbox")
    @patch("agent.sandbox.pipeline.apply_patch")
    @patch("agent.sandbox.pipeline.SandboxWorkspace")
    def test_run_patch_works_directly(
        self, mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr
    ):
        _setup_mocks(mock_ws_cls, mock_apply, mock_validate, mock_git, mock_pr)
        outcome = _make_pipeline().run_patch(
            incident_id=INCIDENT_ID,
            repo_path=REPO_PATH,
            patch=GOOD_PATCH,
            error_type="AssertionError",
            error_message="expected 1, got 3",
        )
        assert outcome.validated is True
        assert outcome.git.branch_name == f"phoenix/fix/{INCIDENT_ID}"


# ============================================================================ #
# Test 11 — summary() output                                                   #
# ============================================================================ #

class TestPatchOutcomeSummary:
    def test_summary_validated_true(self):
        outcome = PatchOutcome(
            incident_id="INC-007",
            validated=True,
            git=_good_git(),
            pull_request=_good_pr(),
            pull_request_url="https://github.com/x/y/pull/42",
        )
        summary = outcome.summary()
        assert "VALIDATED" in summary
        assert "INC-007" in summary
        assert "phoenix/fix/INC-007" in summary

    def test_summary_validated_false(self):
        v = _failing_validation("tests failed")
        outcome = PatchOutcome(
            incident_id="INC-007",
            validated=False,
            validation=v,
        )
        summary = outcome.summary()
        assert "REJECTED" in summary
        assert "INC-007" in summary

    def test_summary_pipeline_error(self):
        outcome = PatchOutcome(
            incident_id="INC-007",
            validated=False,
            error="Unhandled exception: disk full",
        )
        summary = outcome.summary()
        assert "PIPELINE ERROR" in summary or "ERROR" in summary


# ============================================================================ #
# Shared mock setup helper                                                       #
# ============================================================================ #

def _setup_mocks(
    mock_ws_cls,
    mock_apply,
    mock_validate,
    mock_git,
    mock_pr,
    validation=None,
    git=None,
    pr=None,
):
    mock_ws = MagicMock()
    mock_ws.sandbox_path = REPO_PATH
    mock_ws_cls.create.return_value = mock_ws

    mock_apply.return_value = ApplicationResult(success=True, applied_files=["svc.py"])
    mock_validate.return_value = validation or _passing_validation()
    mock_git.return_value = git or _good_git()
    mock_pr.return_value = pr or _good_pr()

    return mock_ws, mock_validate
