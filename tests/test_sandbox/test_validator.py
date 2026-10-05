"""
Phoenix Sandbox Tests — Validator

Tests for agent/sandbox/validator.py.

All subprocess calls are mocked so tests run offline without Docker,
flake8, or pytest installations. The focus is on the orchestration logic,
result assembly, and the original-failure-resolved check.
"""
from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent.sandbox.models import DockerResult, SandboxConfig, ValidationResult
from agent.sandbox.validator import (
    _check_original_failure_resolved,
    _detect_lint_targets,
    _detect_test_paths,
    validate_sandbox,
)
from agent.sandbox.workspace import SandboxWorkspace


# ============================================================================ #
# Helpers                                                                        #
# ============================================================================ #

def _fake_ws(tmp_path: pathlib.Path) -> SandboxWorkspace:
    ws = SandboxWorkspace.__new__(SandboxWorkspace)
    ws._sandbox_root = tmp_path
    ws._repo_root = tmp_path
    ws._cleaned = False
    return ws


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _config(run_lint=True, run_tests=True, run_docker=False) -> SandboxConfig:
    return SandboxConfig(run_lint=run_lint, run_tests=run_tests, run_docker=run_docker)


# ============================================================================ #
# validate_sandbox — full pipeline (mocked subprocesses)                        #
# ============================================================================ #

class TestValidateSandbox:
    def _run(self, tmp_path, lint_rc=0, test_rc=0, test_out="1 passed"):
        ws = _fake_ws(tmp_path)
        cfg = _config()
        with patch("agent.sandbox.validator._run_subprocess") as mock_sub:
            mock_sub.side_effect = [
                _completed(lint_rc),
                _completed(test_rc, stdout=test_out),
            ]
            return validate_sandbox(ws, "INC-007", cfg)

    def test_all_pass_validated_true(self, tmp_path):
        result = self._run(tmp_path)
        assert result.validated is True
        assert result.lint_passed is True
        assert result.tests_passed is True
        assert result.build_passed is True
        assert result.original_failure_resolved is True

    def test_lint_fail_validated_false(self, tmp_path):
        result = self._run(tmp_path, lint_rc=1)
        assert result.validated is False
        assert result.lint_passed is False
        assert "lint" in result.reason

    def test_test_fail_validated_false(self, tmp_path):
        result = self._run(tmp_path, test_rc=1, test_out="FAILED\nTypeError: ...")
        assert result.validated is False
        assert result.tests_passed is False

    def test_result_has_incident_id(self, tmp_path):
        result = self._run(tmp_path)
        assert result.incident_id == "INC-007"

    def test_completed_at_set(self, tmp_path):
        result = self._run(tmp_path)
        assert result.completed_at is not None

    def test_duration_positive(self, tmp_path):
        result = self._run(tmp_path)
        assert result.duration_seconds >= 0.0

    def test_lint_skipped_when_disabled(self, tmp_path):
        ws = _fake_ws(tmp_path)
        cfg = _config(run_lint=False)
        with patch("agent.sandbox.validator._run_subprocess") as mock_sub:
            mock_sub.return_value = _completed(0, stdout="1 passed")
            result = validate_sandbox(ws, "INC-X", cfg)
        assert result.lint_passed is True
        # subprocess called once (tests only, not lint)
        assert mock_sub.call_count == 1

    def test_tests_skipped_when_disabled(self, tmp_path):
        ws = _fake_ws(tmp_path)
        cfg = _config(run_tests=False)
        with patch("agent.sandbox.validator._run_subprocess") as mock_sub:
            mock_sub.return_value = _completed(0)
            result = validate_sandbox(ws, "INC-Y", cfg)
        assert result.tests_passed is True
        assert mock_sub.call_count == 1  # lint only

    def test_docker_result_embedded(self, tmp_path):
        ws = _fake_ws(tmp_path)
        cfg = _config(run_docker=True)
        fake_docker = DockerResult(skipped=True, skip_reason="daemon unavailable")
        with (
            patch("agent.sandbox.validator._run_subprocess") as mock_sub,
            patch("agent.sandbox.validator.run_docker_sandbox", return_value=fake_docker),
        ):
            mock_sub.return_value = _completed(0, stdout="1 passed")
            result = validate_sandbox(ws, "INC-D", cfg)
        assert result.docker is not None
        assert result.docker.skipped is True
        assert result.container_started is True  # skipped counts as ok


# ============================================================================ #
# _check_original_failure_resolved                                               #
# ============================================================================ #

class TestOriginalFailureResolved:
    def _result(self, tests_passed=True, stdout="", stderr="") -> ValidationResult:
        r = ValidationResult(incident_id="INC-T")
        r.tests_passed = tests_passed
        r.test_stdout = stdout
        r.test_stderr = stderr
        return r

    def test_resolved_when_tests_pass_and_error_absent(self):
        r = self._result(tests_passed=True, stdout="1 passed\n")
        assert _check_original_failure_resolved(r, "TypeError", "unsupported operand") is True

    def test_not_resolved_when_tests_fail(self):
        r = self._result(tests_passed=False, stdout="FAILED\nTypeError: unsupported operand\n")
        assert _check_original_failure_resolved(r, "TypeError", "unsupported operand") is False

    def test_not_resolved_when_error_type_in_failure_output(self):
        r = self._result(
            tests_passed=True,
            stdout="FAILED backend/tests/test_x.py::test_y\nE   TypeError: bad thing\n",
        )
        assert _check_original_failure_resolved(r, "TypeError", "") is False

    def test_not_resolved_when_error_message_in_failure_output(self):
        r = self._result(
            tests_passed=True,
            stdout="failed\nunsupported operand type\n",
        )
        assert _check_original_failure_resolved(r, "", "unsupported operand type") is False

    def test_resolved_with_no_error_identifiers(self):
        """No error_type or error_message given — just check tests passed."""
        r = self._result(tests_passed=True, stdout="3 passed\n")
        assert _check_original_failure_resolved(r, "", "") is True


# ============================================================================ #
# Auto-detection helpers                                                         #
# ============================================================================ #

class TestDetectLintTargets:
    def test_prefers_sample_app(self, tmp_path):
        (tmp_path / "sample-app").mkdir()
        assert _detect_lint_targets(tmp_path) == ["sample-app"]

    def test_falls_back_to_backend(self, tmp_path):
        (tmp_path / "backend").mkdir()
        assert _detect_lint_targets(tmp_path) == ["backend"]

    def test_falls_back_to_dot(self, tmp_path):
        assert _detect_lint_targets(tmp_path) == ["."]


class TestDetectTestPaths:
    def test_reads_pytest_ini(self, tmp_path):
        (tmp_path / "pytest.ini").write_text(
            "[pytest]\ntestpaths = sample-app/tests\n", encoding="utf-8"
        )
        (tmp_path / "sample-app" / "tests").mkdir(parents=True)
        assert _detect_test_paths(tmp_path) == ["sample-app/tests"]

    def test_falls_back_to_sample_app_tests(self, tmp_path):
        (tmp_path / "sample-app" / "tests").mkdir(parents=True)
        assert _detect_test_paths(tmp_path) == ["sample-app/tests"]

    def test_falls_back_to_backend_tests(self, tmp_path):
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        assert _detect_test_paths(tmp_path) == ["backend/tests"]

    def test_final_fallback_is_dot(self, tmp_path):
        assert _detect_test_paths(tmp_path) == ["."]
