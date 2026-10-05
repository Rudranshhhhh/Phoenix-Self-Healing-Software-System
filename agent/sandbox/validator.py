"""
Phoenix Sandbox — Patch Validator

Orchestrates all validation steps after the patch has been applied to
the sandbox copy:

  Step 1 — Lint (flake8)
  Step 2 — Tests (pytest)
  Step 3 — Docker build + container health check
  Step 4 — Original failure resolved?

Each step is run inside the sandbox directory. The production repository
is NEVER touched.

Original failure check (Part 5)
--------------------------------
For the MVP we check that:
  a) pytest passes (which proves the previously-failing test now passes), AND
  b) the original error signature / exception type no longer appears in the
     test output.

This is practical and avoids over-engineering: the failing test at
backend/tests/test_incident_severity_count.py explicitly reproduces the
original error; if it now passes, the failure is resolved.

For other error types the check looks for the error_type string (e.g.
"TypeError", "AssertionError") in the pytest failure output and confirms
it is absent.
"""
from __future__ import annotations

import logging
import pathlib
import subprocess
import sys
import time
from typing import Optional

from agent.sandbox.docker_runner import run_docker_sandbox
from agent.sandbox.models import DockerResult, SandboxConfig, ValidationResult
from agent.sandbox.workspace import SandboxWorkspace

logger = logging.getLogger(__name__)


def validate_sandbox(
    workspace: SandboxWorkspace,
    incident_id: str,
    config: SandboxConfig,
    original_error_type: str = "",
    original_error_message: str = "",
) -> ValidationResult:
    """
    Run the full validation pipeline inside the sandbox.

    Args:
        workspace:              The patched sandbox workspace.
        incident_id:            For identification in the result.
        config:                 Validation configuration (timeouts, flags, etc.).
        original_error_type:    e.g. "TypeError" — used to verify the
                                original failure is gone.
        original_error_message: e.g. "unsupported operand" — used as secondary
                                check that the error no longer appears.

    Returns:
        ValidationResult with compute_validated() already called.
    """
    result = ValidationResult(incident_id=incident_id)
    sandbox = workspace.sandbox_path

    # ------------------------------------------------------------------ #
    # Step 1 — Lint                                                        #
    # ------------------------------------------------------------------ #
    if config.run_lint:
        _run_lint(sandbox, config, result)
    else:
        result.lint_passed = True
        logger.info("Validator: lint step skipped (config.run_lint=False)")

    # ------------------------------------------------------------------ #
    # Step 2 — Tests                                                       #
    # ------------------------------------------------------------------ #
    if config.run_tests:
        _run_tests(sandbox, config, result)
    else:
        result.tests_passed = True
        logger.info("Validator: test step skipped (config.run_tests=False)")

    # ------------------------------------------------------------------ #
    # Step 3 — Docker sandbox                                              #
    # ------------------------------------------------------------------ #
    if config.run_docker:
        docker_result = run_docker_sandbox(
            sandbox_path=sandbox,
            incident_id=incident_id,
            dockerfile_path=config.dockerfile_path,
            docker_timeout_seconds=config.docker_timeout_seconds,
            container_startup_timeout=config.container_startup_timeout,
            skip_if_unavailable=config.skip_docker_if_unavailable,
        )
        result.docker = docker_result
        result.container_started = docker_result.container_started or docker_result.skipped
        logger.info(
            "Validator: Docker step — build=%s container=%s skipped=%s",
            docker_result.build_passed,
            docker_result.container_started,
            docker_result.skipped,
        )
    else:
        result.container_started = True
        logger.info("Validator: Docker step skipped (config.run_docker=False)")

    # ------------------------------------------------------------------ #
    # Step 4 — Original failure resolved?                                  #
    # ------------------------------------------------------------------ #
    result.original_failure_resolved = _check_original_failure_resolved(
        result=result,
        original_error_type=original_error_type,
        original_error_message=original_error_message,
    )

    # build_passed is true if both lint and tests are ok
    result.build_passed = result.lint_passed and result.tests_passed

    # ------------------------------------------------------------------ #
    # Finalise                                                             #
    # ------------------------------------------------------------------ #
    result.compute_validated()
    logger.info(
        "Validator: %s — validated=%s (%s)",
        incident_id,
        result.validated,
        result.reason,
    )
    return result


# ============================================================================ #
# Step implementations                                                           #
# ============================================================================ #

def _run_lint(
    sandbox: pathlib.Path,
    config: SandboxConfig,
    result: ValidationResult,
) -> None:
    """Run flake8 inside the sandbox. Updates result in place."""
    lint_targets = config.lint_targets or _detect_lint_targets(sandbox)
    flake8_config = _find_flake8_config(sandbox)

    cmd = [sys.executable, "-m", "flake8"] + lint_targets
    if flake8_config:
        cmd += ["--config", str(flake8_config)]

    logger.info("Validator: running lint — %s (cwd=%s)", " ".join(cmd), sandbox)

    proc = _run_subprocess(cmd, cwd=sandbox, timeout=config.lint_timeout_seconds)
    result.lint_stdout = proc.stdout or ""
    result.lint_stderr = proc.stderr or ""
    result.lint_exit_code = proc.returncode
    result.lint_passed = proc.returncode == 0

    if result.lint_passed:
        logger.info("Validator: lint PASSED")
    else:
        logger.warning(
            "Validator: lint FAILED (exit %d)\n%s",
            proc.returncode,
            (result.lint_stdout + result.lint_stderr)[:800],
        )


def _run_tests(
    sandbox: pathlib.Path,
    config: SandboxConfig,
    result: ValidationResult,
) -> None:
    """Run pytest inside the sandbox. Updates result in place."""
    test_paths = config.test_paths or _detect_test_paths(sandbox)

    cmd = [
        sys.executable, "-m", "pytest",
        "--tb=short",
        "-v",
        "--no-header",
    ] + test_paths

    logger.info("Validator: running tests — %s (cwd=%s)", " ".join(cmd), sandbox)

    proc = _run_subprocess(cmd, cwd=sandbox, timeout=config.test_timeout_seconds)
    result.test_stdout = proc.stdout or ""
    result.test_stderr = proc.stderr or ""
    result.test_exit_code = proc.returncode
    result.tests_passed = proc.returncode == 0

    if result.tests_passed:
        logger.info("Validator: tests PASSED")
    else:
        logger.warning(
            "Validator: tests FAILED (exit %d)\n%s",
            proc.returncode,
            (result.test_stdout + result.test_stderr)[:800],
        )


def _check_original_failure_resolved(
    result: ValidationResult,
    original_error_type: str,
    original_error_message: str,
) -> bool:
    """
    Determine whether the original failure is no longer present.

    Logic (MVP-level, practical):
    1. If tests did not pass, the original failure is by definition NOT resolved
       (because the test that reproduces the bug is still failing).
    2. If tests passed AND the original_error_type still appears as a pytest
       FAILURE line in the test output, consider it unresolved.
    3. If tests passed AND no trace of the original error in the output → resolved.

    This avoids the need for a separate "run the old test" step; the existing
    pytest suite is the canonical oracle.
    """
    if not result.tests_passed:
        return False

    # Tests passed — verify the original error signature is absent
    combined_output = (result.test_stdout + result.test_stderr).lower()

    if original_error_type:
        # Pytest marks failures with "FAILED" and shows the error type.
        # If the error type still appears in a failure context, it's unresolved.
        error_lower = original_error_type.lower()
        # Only flag it if it appears alongside a "failed" or "error" marker
        suspicious_lines = [
            line for line in combined_output.splitlines()
            if error_lower in line and any(
                kw in line for kw in ("failed", "error", "e   ")
            )
        ]
        if suspicious_lines:
            logger.warning(
                "Validator: original error type %r still appears in failing test output",
                original_error_type,
            )
            return False

    if original_error_message:
        # Check for the core message snippet (first 60 chars, lowercased)
        snippet = original_error_message.lower()[:60]
        if snippet in combined_output and "failed" in combined_output:
            logger.warning(
                "Validator: original error message snippet still present in output"
            )
            return False

    return True


# ============================================================================ #
# Detection helpers                                                              #
# ============================================================================ #

def _detect_lint_targets(sandbox: pathlib.Path) -> list[str]:
    """
    Auto-detect what to lint.

    Priority:
      1. sample-app/  (Phoenix sample app — what CI lints)
      2. backend/
      3. agent/
      4. "." (everything)
    """
    for candidate in ("sample-app", "backend", "agent"):
        if (sandbox / candidate).is_dir():
            return [candidate]
    return ["."]


def _detect_test_paths(sandbox: pathlib.Path) -> list[str]:
    """
    Auto-detect pytest test paths.

    Reads pytest.ini testpaths if present; otherwise falls back to known
    Phoenix test directories.
    """
    # Try reading pytest.ini
    ini = sandbox / "pytest.ini"
    if ini.exists():
        try:
            content = ini.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("testpaths"):
                    _, _, value = stripped.partition("=")
                    paths = value.strip().split()
                    if paths:
                        # Verify at least one exists
                        if any((sandbox / p).exists() for p in paths):
                            return paths
        except OSError:
            pass

    # Fallback: check known paths in priority order
    for candidate in (
        "sample-app/tests",
        "backend/tests",
        "tests",
    ):
        if (sandbox / candidate).is_dir():
            return [candidate]

    return ["."]


def _find_flake8_config(sandbox: pathlib.Path) -> Optional[pathlib.Path]:
    """Return the .flake8 config path inside the sandbox, if it exists."""
    candidate = sandbox / ".flake8"
    return candidate if candidate.exists() else None


# ============================================================================ #
# Subprocess runner                                                              #
# ============================================================================ #

def _run_subprocess(
    cmd: list[str],
    cwd: pathlib.Path,
    timeout: int,
) -> subprocess.CompletedProcess:
    """Run a subprocess, capturing output, never raising on non-zero exit."""
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Validator: command timed out after %ds: %s", timeout, cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"Command timed out after {timeout}s.",
        )
    except FileNotFoundError as exc:
        logger.error("Validator: command not found: %s", exc)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )
    except Exception as exc:
        logger.error("Validator: unexpected subprocess error: %s", exc)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=str(exc),
        )
