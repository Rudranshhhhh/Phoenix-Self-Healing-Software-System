"""
Phoenix API — Evidence Extraction

Thin adapter: convert CI payloads and Docker incidents into EvidenceInput
for the existing LLM engine.
"""
import logging
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
