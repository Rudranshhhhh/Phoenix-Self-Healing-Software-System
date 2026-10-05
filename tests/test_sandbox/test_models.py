"""
Phoenix Sandbox Tests — Models

Tests for agent/sandbox/models.py.
Pure unit tests — no I/O, no subprocess calls.
"""
from __future__ import annotations

import pytest

from agent.sandbox.models import (
    DockerResult,
    GitResult,
    PRResult,
    PatchOutcome,
    SandboxConfig,
    ValidationResult,
)


class TestValidationResultComputeValidated:
    def _full_pass(self) -> ValidationResult:
        r = ValidationResult(incident_id="INC-T")
        r.build_passed = True
        r.lint_passed = True
        r.tests_passed = True
        r.container_started = True
        r.original_failure_resolved = True
        return r

    def test_all_pass_validated_true(self):
        r = self._full_pass()
        r.compute_validated()
        assert r.validated is True
        assert r.reason == "All validation checks passed."

    def test_lint_fail_validated_false(self):
        r = self._full_pass()
        r.lint_passed = False
        r.compute_validated()
        assert r.validated is False
        assert "lint" in r.reason

    def test_tests_fail_validated_false(self):
        r = self._full_pass()
        r.tests_passed = False
        r.compute_validated()
        assert r.validated is False
        assert "tests" in r.reason

    def test_original_failure_not_resolved_validated_false(self):
        r = self._full_pass()
        r.original_failure_resolved = False
        r.compute_validated()
        assert r.validated is False
        assert "original failure" in r.reason

    def test_docker_container_not_started_validated_false(self):
        r = self._full_pass()
        r.docker = DockerResult(skipped=False, container_started=False)
        r.container_started = False
        r.compute_validated()
        assert r.validated is False

    def test_docker_skipped_does_not_block_validation(self):
        r = self._full_pass()
        r.docker = DockerResult(skipped=True, skip_reason="daemon unavailable")
        r.container_started = True  # skipped → counts as ok
        r.compute_validated()
        assert r.validated is True

    def test_completed_at_set_after_compute(self):
        r = self._full_pass()
        r.compute_validated()
        assert r.completed_at is not None

    def test_duration_set_after_compute(self):
        r = self._full_pass()
        r.compute_validated()
        assert r.duration_seconds >= 0.0

    def test_multiple_failures_listed_in_reason(self):
        r = self._full_pass()
        r.lint_passed = False
        r.tests_passed = False
        r.compute_validated()
        assert "lint" in r.reason
        assert "tests" in r.reason


class TestValidationResultToPRSection:
    def test_contains_pass_icons_when_all_pass(self):
        r = ValidationResult(incident_id="INC-T")
        r.build_passed = True
        r.lint_passed = True
        r.tests_passed = True
        r.container_started = True
        r.original_failure_resolved = True
        section = r.to_pr_section()
        assert "✅ PASS" in section

    def test_contains_fail_icon_when_lint_fails(self):
        r = ValidationResult(incident_id="INC-T")
        r.lint_passed = False
        section = r.to_pr_section()
        assert "❌ FAIL" in section

    def test_contains_skipped_when_docker_skipped(self):
        r = ValidationResult(incident_id="INC-T")
        r.docker = DockerResult(skipped=True, skip_reason="no daemon")
        section = r.to_pr_section()
        assert "SKIPPED" in section


class TestSandboxConfig:
    def test_default_flags_true(self):
        cfg = SandboxConfig()
        assert cfg.run_lint is True
        assert cfg.run_tests is True
        assert cfg.run_docker is True
        assert cfg.skip_docker_if_unavailable is True

    def test_can_disable_docker(self):
        cfg = SandboxConfig(run_docker=False)
        assert cfg.run_docker is False

    def test_default_timeouts_positive(self):
        cfg = SandboxConfig()
        assert cfg.docker_timeout_seconds > 0
        assert cfg.lint_timeout_seconds > 0
        assert cfg.test_timeout_seconds > 0


class TestGitResult:
    def test_branch_name_set(self):
        g = GitResult(success=True, branch_name="phoenix/fix/INC-007", commit_sha="abc123")
        assert g.branch_name == "phoenix/fix/INC-007"

    def test_failed_git_result(self):
        g = GitResult(success=False, error="push rejected")
        assert g.success is False
        assert "push rejected" in g.error


class TestPRResult:
    def test_success_pr(self):
        p = PRResult(success=True, pr_number=42, pr_url="https://github.com/x/y/pull/42")
        assert p.pr_number == 42

    def test_failed_pr(self):
        p = PRResult(success=False, error="GITHUB_TOKEN not set")
        assert p.success is False


class TestPatchOutcome:
    def test_incident_id_required(self):
        o = PatchOutcome(incident_id="INC-007")
        assert o.incident_id == "INC-007"

    def test_ran_at_set_automatically(self):
        o = PatchOutcome(incident_id="INC-007")
        assert o.ran_at is not None

    def test_pull_request_url_shortcut(self):
        o = PatchOutcome(
            incident_id="INC-007",
            validated=True,
            pull_request_url="https://github.com/x/y/pull/1",
        )
        assert o.pull_request_url == "https://github.com/x/y/pull/1"
