"""
Phoenix API — Evidence Extraction

Thin adapter: convert CI payloads and Docker incidents into EvidenceInput
for the existing LLM engine.
"""
import logging
import pathlib
import re
from typing import Optional

from agent.ai.llm_engine.diagnosis import EvidenceInput

logger = logging.getLogger(__name__)


def extract_evidence_from_ci_payload(
    payload: dict,
) -> Optional[EvidenceInput]:
    """
    Extract EvidenceInput from a GitHub Actions CI webhook payload.

    The payload contains:
    - repository, commit, branch
    - run_id, run_url, workflow
    - stage (lint, build, test)
    - logs (truncated output)

    We construct evidence from the logs and metadata.
    """
    try:
        logs = payload.get("logs", "")
        stage = payload.get("stage", "test")

        # Extract error type and message from logs if possible
        error_type, error_message = _parse_error_from_logs(logs)

        # Try to find relevant code snippets in logs
        code_snippet = _extract_code_snippet(logs)

        return EvidenceInput(
            error_type=error_type,
            error_message=error_message,
            file="unknown",  # logs don't usually contain the exact file
            line=0,
            relevant_code=code_snippet,
            stack_trace=logs[:2000],  # truncate to avoid huge tokens
            extra_context={
                "source": "github_ci",
                "repository": payload.get("repository"),
                "commit": payload.get("commit"),
                "branch": payload.get("branch"),
                "run_id": payload.get("run_id"),
                "workflow": payload.get("workflow"),
                "stage": stage,
            },
        )
    except Exception as exc:
        logger.error("Failed to extract evidence from CI payload: %s", exc)
        return None


def extract_evidence_from_docker_incident(
    payload: dict,
) -> Optional[EvidenceInput]:
    """
    Extract EvidenceInput from a Docker runtime incident.

    The payload contains:
    - error_type, error_message
    - logs, stack_trace
    - repository, commit, branch
    - container_name

    Uses the existing EvidenceInput model from agent.ai.llm_engine.
    """
    try:
        return EvidenceInput(
            error_type=payload.get("error_type", "RuntimeError"),
            error_message=payload.get("error_message", "Unknown error"),
            file="unknown",
            line=0,
            relevant_code=None,
            stack_trace=payload.get("stack_trace"),
            extra_context={
                "source": "docker_runtime",
                "repository": payload.get("repository"),
                "commit": payload.get("commit"),
                "branch": payload.get("branch"),
                "container": payload.get("container_name"),
                "logs": payload.get("logs", "")[:1000],  # truncate
            },
        )
    except Exception as exc:
        logger.error("Failed to extract evidence from Docker payload: %s", exc)
        return None


def enrich_evidence_from_repository(
    evidence: EvidenceInput,
    repo_path: pathlib.Path,
) -> EvidenceInput:
    """Resolve traceback locations and attach bounded source context.

    Logs are useful for identifying a failure but are not sufficient for safe
    patch generation. This helper reads only the referenced source file and a
    small window around the failing line, keeping prompts compact.
    """
    stack_trace = evidence.stack_trace or ""
    match = None
    for candidate in re.finditer(r'File ["\']([^"\']+)["\'], line (\d+)', stack_trace):
        match = candidate
    if match is None:
        return evidence

    raw_file = match.group(1).replace("\\", "/")
    relative_file = raw_file
    marker = "/workspace/"
    if marker in relative_file:
        relative_file = relative_file.split(marker, 1)[1]
    while relative_file.startswith("./"):
        relative_file = relative_file[2:]
    source_file = (repo_path / relative_file).resolve()
    try:
        source_file.relative_to(repo_path.resolve())
    except ValueError:
        logger.warning("Ignoring traceback path outside repository: %s", raw_file)
        return evidence
    if not source_file.is_file():
        return evidence

    line = int(match.group(2))
    try:
        lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("Could not read evidence source %s: %s", source_file, exc)
        return evidence

    start = max(0, line - 8)
    end = min(len(lines), line + 7)
    snippet = "\n".join(lines[start:end])
    return evidence.model_copy(
        update={
            "file": source_file.relative_to(repo_path.resolve()).as_posix(),
            "line": line,
            "relevant_code": snippet,
        }
    )


# ============================================================================ #
# Helper functions to parse logs                                              #
# ============================================================================ #


def _parse_error_from_logs(logs: str) -> tuple[str, str]:
    """
    Parse error type and message from CI logs.
    Returns (error_type, error_message).
    """
    if not logs:
        return "UnknownError", "Build or test failed"

    lines = logs.split("\n")

    # Look for Python exceptions (TypeError:, AssertionError:, etc.)
    for line in lines:
        line_lower = line.lower()
        if "error" in line_lower or "failed" in line_lower:
            # Try to extract error type
            for exc_type in (
                "TypeError",
                "AssertionError",
                "ValueError",
                "KeyError",
                "AttributeError",
                "ImportError",
                "RuntimeError",
                "IndexError",
            ):
                if exc_type in line:
                    # Extract message after the colon
                    if ":" in line:
                        msg = line.split(":", 1)[1].strip()
                        return exc_type, msg
                    return exc_type, line
    
    # Look for any "failed" message
    for line in lines[-10:]:  # check last 10 lines
        if "failed" in line.lower():
            return "BuildFailure", line.strip()

    return "UnknownFailure", "Build or test failed (see logs)"


def _extract_code_snippet(logs: str) -> Optional[str]:
    """
    Try to extract relevant code from logs.
    Returns the first code block or None.
    """
    if not logs:
        return None
    lines = logs.split("\n")
    code_lines = []
    in_code = False
    for line in lines:
        # Simple heuristic: code indented or contains Python syntax
        if line.strip().startswith(("def ", "class ", "if ", "for ", "while ", "import ", "from ")):
            in_code = True
        if in_code:
            code_lines.append(line)
            if len(code_lines) > 20:
                break
    if code_lines:
        return "\n".join(code_lines[:20])
    return None
