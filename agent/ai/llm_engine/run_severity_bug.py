"""
Phoenix LLM Engine — REAL bug runner: severity-count mismatch.

Feeds the actual failing test
    backend/tests/test_incident_severity_count.py::test_severity_filter_applies_to_total_count
through the EXISTING Phoenix LLM Engine (engine.py -> diagnosis.py -> patch.py)
and prints the DiagnosisResult and PatchResult.

DO NOT apply the generated patch. This script only produces a proposal.

Usage
-----
  # Real Groq run (requires GROQ_API_KEY in the environment):
  python -m agent.ai.llm_engine.run_severity_bug

  # Offline plumbing dry-run using the existing MockLLMClient:
  python -m agent.ai.llm_engine.run_severity_bug --mock

The EvidenceInput is built from the REAL failure:
  - error_type / error_message / file / line from the pytest AssertionError
  - relevant_code: the raw list_incidents (service) + count_incidents (repo)
  - stack_trace: the real pytest traceback
  - extra_context: service<->repository relationship + test expectation + seeded data
"""
from __future__ import annotations

import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phoenix.run_severity_bug")

from agent.ai.llm_engine.diagnosis import EvidenceInput
from agent.ai.llm_engine.engine import LLMEngine
from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.mock_client import MockLLMClient


# ============================================================================ #
# Real failure evidence                                                          #
# ============================================================================ #

RELEVANT_CODE = """\
# FILE: backend/services/incident_service.py   (function: list_incidents)
def list_incidents(
    service: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    skip = (page - 1) * page_size
    items = repo.list_incidents(
        service=service,
        status=status,
        severity=severity,
        resolved=resolved,
        limit=page_size,
        skip=skip,
    )
    total = repo.count_incidents(service=service, status=status, resolved=resolved)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


# FILE: backend/repositories/incident_repository.py   (function: count_incidents)
def count_incidents(
    service: Optional[str] = None,
    status: Optional[str] = None,
    resolved: Optional[bool] = None,
) -> int:
    query: dict = {}
    if service:
        query["service"] = service
    if status:
        query["status"] = status
    if resolved is not None:
        query["resolved"] = resolved
    return mongo.incidents().count_documents(query)
"""

STACK_TRACE = """\
FAILED backend/tests/test_incident_severity_count.py::test_severity_filter_applies_to_total_count

    result = incident_service.list_incidents(severity="HIGH", page=1, page_size=20)
    assert len(result["items"]) == 1
    assert result["items"][0]["severity"] == "HIGH"
    assert result["items"][0]["incident_id"] == "inc-high-1"
>   assert result["total"] == 1, (
        f"expected total = 1 (only HIGH incidents), actual total = {result['total']}"
    )
E   AssertionError: expected total = 1 (only HIGH incidents), actual total = 3
E   assert 3 == 1
backend\\tests\\test_incident_severity_count.py:164: AssertionError
"""


def build_evidence() -> EvidenceInput:
    """Construct the EvidenceInput from the real failing test."""
    return EvidenceInput(
        error_type="AssertionError",
        error_message="expected total = 1 (only HIGH incidents), actual total = 3",
        file="backend/services/incident_service.py",
        line=54,
        function_name="list_incidents",
        relevant_code=RELEVANT_CODE,
        stack_trace=STACK_TRACE,
        extra_context={
            "monitored_app": "MoodOS backend (Flask + MongoDB)",
            "service_layer": (
                "backend/services/incident_service.py holds business logic and "
                "delegates data access to the repository layer."
            ),
            "repository_layer": (
                "backend/repositories/incident_repository.py exposes "
                "list_incidents() and count_incidents() over the incidents "
                "MongoDB collection."
            ),
            "test": (
                "backend/tests/test_incident_severity_count.py::"
                "test_severity_filter_applies_to_total_count asserts that "
                "filtering by severity narrows BOTH the returned items AND the "
                "`total` used for pagination."
            ),
            "seeded_data": "3 incidents: 2 with severity=LOW, 1 with severity=HIGH",
            "test_call": "incident_service.list_incidents(severity='HIGH', page=1, page_size=20)",
            "observed": "items correctly contains 1 HIGH incident; total reports 3",
        },
    )


# ============================================================================ #
# Reporting helpers                                                              #
# ============================================================================ #

_THICK = "=" * 78


def _print_evidence(ev: EvidenceInput) -> None:
    print(f"\n{_THICK}\n  EVIDENCE INPUT (real failure)\n{_THICK}")
    print(f"  error_type    : {ev.error_type}")
    print(f"  error_message : {ev.error_message}")
    print(f"  file          : {ev.file}:{ev.line}")
    print(f"  function      : {ev.function_name}")
    print(f"\n  relevant_code :\n{ev.relevant_code}")
    print(f"\n  stack_trace :\n{ev.stack_trace}")
    print("  extra_context :")
    for k, v in ev.extra_context.items():
        print(f"    {k}: {v}")


def _print_diagnosis(d) -> None:
    print(f"\n{_THICK}\n  DIAGNOSIS RESULT\n{_THICK}")
    if d is None:
        print("  (no diagnosis returned)")
        return
    print(f"  root_cause     : {d.root_cause}")
    print(f"  explanation    : {d.explanation}")
    print(f"  affected_file  : {d.affected_file}")
    print(f"  affected_line  : {d.affected_line}")
    print(f"  confidence     : {d.confidence * 100:.0f}%")


def _print_patch(p) -> None:
    print(f"\n{_THICK}\n  PATCH RESULT\n{_THICK}")
    if p is None:
        print("  (no patch returned — generation or validation failed)")
        return
    print(f"  is_empty     : {p.is_empty}")
    print(f"  patch count  : {len(p.patches)}")
    for i, fp in enumerate(p.patches, 1):
        print(f"  [{i}] file     : {fp.file}")
        print(f"      old_code : {fp.old_code!r}")
        print(f"      new_code : {fp.new_code!r}")
    print(f"  explanation  : {p.explanation}")


def _print_validation(result) -> None:
    print(f"\n{_THICK}\n  PIPELINE STATUS\n{_THICK}")
    print(f"  success : {result.success}")
    print(f"  error   : {result.error}")
    print(result.summary())


# ============================================================================ #
# Main                                                                          #
# ============================================================================ #

def main() -> None:
    use_mock = "--mock" in sys.argv[1:]

    evidence = build_evidence()
    _print_evidence(evidence)

    # ------------------------------------------------------------------ #
    # Choose client: real Groq by default; MockLLMClient only with --mock #
    # ------------------------------------------------------------------ #
    if use_mock:
        print(f"\n{_THICK}\n  *** MOCK DRY-RUN (MockLLMClient) — NOT a real Groq response ***\n{_THICK}")
        client = MockLLMClient()
    else:
        if not os.environ.get("GROQ_API_KEY"):
            print(
                f"\n{_THICK}\n  GROQ_API_KEY is not set — cannot run against real Groq.\n"
                f"  Set it and re-run:\n"
                f"     PowerShell : $env:GROQ_API_KEY = 'gsk_...'\n"
                f"     then       : python -m agent.ai.llm_engine.run_severity_bug\n"
                f"  Or run an offline plumbing check with --mock.\n{_THICK}"
            )
            sys.exit(2)
        print(f"\n{_THICK}\n  REAL GROQ RUN (GroqLLMClient, model loaded from env)\n{_THICK}")
        client = GroqLLMClient()

    # Use the EXISTING pipeline (LLMEngine.run -> generate_diagnosis -> generate_patch)
    engine = LLMEngine(client=client)
    result = engine.run(evidence)

    _print_diagnosis(result.diagnosis)
    _print_patch(result.patch)
    _print_validation(result)

    # Full JSON for transparency (API key never printed)
    print(f"\n{_THICK}\n  FULL JSON OUTPUT\n{_THICK}")
    out = {
        "success": result.success,
        "error": result.error,
        "diagnosis": result.diagnosis.model_dump() if result.diagnosis else None,
        "patch": (
            result.patch.model_dump(exclude={"is_empty"})
            if result.patch else None
        ),
    }
    for line in json.dumps(out, indent=2).splitlines():
        print(f"  {line}")


if __name__ == "__main__":
    main()
