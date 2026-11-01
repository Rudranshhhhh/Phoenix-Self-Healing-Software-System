"""
Phoenix API — Evidence Extraction

Converts CI payloads and Docker incidents into EvidenceInput for the LLM engine.
Supports Python tracebacks, TypeScript tsc errors, ESLint, Jest, and pytest.
"""
from __future__ import annotations

import logging
import pathlib
import re
from typing import Optional

from agent.ai.llm_engine.diagnosis import EvidenceInput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for different error formats
# ---------------------------------------------------------------------------

# Python: File "path/to/file.py", line 42, in function
_PY_TRACEBACK = re.compile(r'File ["\']([^"\']+)["\'], line (\d+)')

# TypeScript tsc: src/phoenix-bug.ts(7,14): error TS2322: Type 'string' ...
_TS_ERROR = re.compile(r'([^\s(]+\.[jt]sx?)\((\d+),\d+\): error (TS\d+): (.+)')

# ESLint: path/to/file.js:10:5: error Description
_ESLINT = re.compile(r'([^\s]+\.[jt]sx?):(\d+):\d+: error (.+)')

# pytest: FAILED tests/test_foo.py::test_bar - AssertionError: ...
_PYTEST = re.compile(r'FAILED ([^\s]+\.py)::(\w+)\s*[-–]\s*(.+)')

# Jest: ● TestSuite > test name  (or FAIL src/App.test.tsx)
_JEST_FAIL = re.compile(r'FAIL\s+([^\s]+\.[jt]sx?)')


# ---------------------------------------------------------------------------
# Public: extract from CI payload
# ---------------------------------------------------------------------------

def extract_evidence_from_ci_payload(payload: dict) -> Optional[EvidenceInput]:
    """Convert a GitHub Actions CI webhook payload into EvidenceInput."""
    try:
        logs  = payload.get("logs", "")
        stage = payload.get("stage", "test")

        error_type, error_message, file_hint, line_hint = _parse_ci_logs(logs, stage)

        return EvidenceInput(
            error_type=error_type,
            error_message=error_message,
            file=file_hint or "unknown",
            line=line_hint or 0,
            relevant_code=None,          # filled in by enrich_evidence_from_repository
            stack_trace=logs[:4000],
            extra_context={
                "source":     "github_ci",
                "repository": payload.get("repository"),
                "commit":     payload.get("commit"),
                "branch":     payload.get("branch"),
                "run_id":     payload.get("run_id"),
                "workflow":   payload.get("workflow"),
                "stage":      stage,
            },
        )
    except Exception as exc:
        logger.error("Failed to extract CI evidence: %s", exc)
        return None


def extract_evidence_from_docker_incident(payload: dict) -> Optional[EvidenceInput]:
    """Convert a Docker runtime incident payload into EvidenceInput."""
    try:
        return EvidenceInput(
            error_type=payload.get("error_type", "RuntimeError"),
            error_message=payload.get("error_message", "Unknown error"),
            file="unknown",
            line=0,
            relevant_code=None,
            stack_trace=payload.get("stack_trace"),
            extra_context={
                "source":    "docker_runtime",
                "repository": payload.get("repository"),
                "commit":    payload.get("commit"),
                "branch":    payload.get("branch"),
                "container": payload.get("container_name"),
                "logs":      payload.get("logs", "")[:1000],
            },
        )
    except Exception as exc:
        logger.error("Failed to extract Docker evidence: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public: enrich with actual source code from cloned repo
# ---------------------------------------------------------------------------

def enrich_evidence_from_repository(
    evidence: EvidenceInput,
    repo_path: pathlib.Path,
) -> EvidenceInput:
    """
    Attach actual source code context to the evidence by reading the file
    referenced in the error from the cloned repository.

    Handles both Python tracebacks and TypeScript/JS errors.
    Falls back to scanning all error-referenced files when a single file
    cannot be resolved.
    """
    stack = evidence.stack_trace or ""
    updates: dict = {}

    # ── Try TypeScript / ESLint (has explicit file path in error message) ──
    for pattern in (_TS_ERROR, _ESLINT):
        m = pattern.search(stack)
        if m:
            raw_file = m.group(1).replace("\\", "/").lstrip("/")
            line_no  = int(m.group(2))
            snippet  = _read_snippet(repo_path, raw_file, line_no)
            if snippet:
                updates = {"file": raw_file, "line": line_no, "relevant_code": snippet}
                logger.info("enrich: resolved TS/ESLint file=%s line=%d", raw_file, line_no)
                break

    # ── If not found, try Python traceback ────────────────────────────────
    if not updates:
        last_py = None
        for m in _PY_TRACEBACK.finditer(stack):
            last_py = m
        if last_py:
            raw_file = last_py.group(1).replace("\\", "/")
            for prefix in ("/workspace/", "./"):
                if raw_file.startswith(prefix):
                    raw_file = raw_file[len(prefix):]
            line_no = int(last_py.group(2))
            snippet = _read_snippet(repo_path, raw_file, line_no)
            if snippet:
                updates = {"file": raw_file, "line": line_no, "relevant_code": snippet}
                logger.info("enrich: resolved Python file=%s line=%d", raw_file, line_no)

    # ── If evidence already has a file hint from _parse_ci_logs ──────────
    if not updates and evidence.file and evidence.file != "unknown":
        snippet = _read_snippet(repo_path, evidence.file, evidence.line or 1)
        if snippet:
            updates = {"relevant_code": snippet}
            logger.info("enrich: used pre-parsed file hint %s", evidence.file)

    # ── Last resort: collect all TS/JS files mentioned in the logs ────────
    if not updates:
        blocks: list[str] = []
        seen: set[str] = set()
        for m in list(_TS_ERROR.finditer(stack)) + list(_ESLINT.finditer(stack)):
            f = m.group(1).replace("\\", "/").lstrip("/")
            if f in seen:
                continue
            seen.add(f)
            content = _read_file_full(repo_path, f)
            if content:
                blocks.append(f"# FILE: {f}\n{content[:2000]}")
        if blocks:
            updates = {"relevant_code": "\n\n".join(blocks)}
            logger.info("enrich: attached %d file(s) from TS error scan", len(blocks))

    if updates:
        return evidence.model_copy(update=updates)
    return evidence


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_snippet(repo_path: pathlib.Path, relative: str, line: int, context: int = 10) -> Optional[str]:
    """Read ±context lines around `line` in `relative` from `repo_path`."""
    path = _safe_resolve(repo_path, relative)
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, line - context - 1)
        end   = min(len(lines), line + context)
        return "\n".join(lines[start:end])
    except OSError:
        return None


def _read_file_full(repo_path: pathlib.Path, relative: str, max_chars: int = 3000) -> Optional[str]:
    """Read the full content of a file (truncated to max_chars)."""
    path = _safe_resolve(repo_path, relative)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return None


def _safe_resolve(repo_path: pathlib.Path, relative: str) -> Optional[pathlib.Path]:
    """Resolve a relative path inside repo_path; return None on traversal or missing."""
    candidate = (repo_path / relative).resolve()
    try:
        candidate.relative_to(repo_path.resolve())
    except ValueError:
        logger.warning("Path traversal blocked: %s", relative)
        return None
    return candidate if candidate.is_file() else None


def _parse_ci_logs(logs: str, stage: str) -> tuple[str, str, Optional[str], Optional[int]]:
    """
    Parse CI logs to extract (error_type, error_message, file, line).
    Handles TypeScript, Python, Jest, pytest, generic build failures.
    """
    if not logs:
        return "UnknownFailure", "Build failed (no logs)", None, None

    # TypeScript tsc error
    m = _TS_ERROR.search(logs)
    if m:
        return f"TS{m.group(3)}", m.group(4).strip(), m.group(1), int(m.group(2))

    # ESLint
    m = _ESLINT.search(logs)
    if m:
        return "ESLintError", m.group(3).strip(), m.group(1), int(m.group(2))

    # pytest FAILED
    m = _PYTEST.search(logs)
    if m:
        return "TestFailure", m.group(3).strip(), m.group(1), None

    # Python exception in traceback
    for line in logs.splitlines():
        for exc in ("TypeError","AssertionError","ValueError","KeyError",
                    "AttributeError","ImportError","RuntimeError","IndexError",
                    "NameError","ZeroDivisionError"):
            if exc in line and ":" in line:
                return exc, line.split(":", 1)[1].strip()[:200], None, None

    # Generic build/test failure
    for line in reversed(logs.splitlines()[-20:]):
        if "error" in line.lower() or "failed" in line.lower():
            return "BuildFailure", line.strip()[:200], None, None

    stage_map = {
        "typecheck": "TypeScriptError",
        "lint":      "LintError",
        "test":      "TestFailure",
        "build":     "BuildFailure",
        "pytest":    "TestFailure",
    }
    return stage_map.get(stage, "CIFailure"), f"{stage} stage failed", None, None
