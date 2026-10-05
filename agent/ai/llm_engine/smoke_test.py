"""
Phoenix LLM Engine — Smoke Test

Standalone script that exercises the full LLMEngine pipeline against mock
MoodOS evidence. Run this directly to verify the module works end-to-end
before integrating with the rest of Phoenix.

Prerequisites
-------------
  1. Set the GROQ_API_KEY environment variable:
         $env:GROQ_API_KEY = "gsk_..."          (PowerShell)
         export GROQ_API_KEY="gsk_..."           (bash)

  2. Install dependencies from the agent directory:
         pip install -r requirements.txt

Usage
-----
  # Run all 5 scenarios
  python -m agent.ai.llm_engine.smoke_test

  # Run a single scenario by name
  python -m agent.ai.llm_engine.smoke_test type_error

  # Run a single scenario by index (0-based)
  python -m agent.ai.llm_engine.smoke_test 2

  # List available scenario names
  python -m agent.ai.llm_engine.smoke_test --list

Output
------
  A human-readable report for each scenario showing:
  - The input evidence
  - Whether the LLM call succeeded
  - The root cause and confidence
  - The proposed old_code → new_code patch
  - The full JSON output (for debugging)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

# Configure logging before any Phoenix imports so all module logs are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phoenix.llm_engine.smoke_test")

from agent.ai.llm_engine.engine import LLMEngine
from agent.ai.llm_engine.mock_evidence import SCENARIOS, list_scenarios, get_scenario


# ============================================================================ #
# Formatting helpers                                                             #
# ============================================================================ #

_SEPARATOR = "─" * 72
_THICK_SEP = "═" * 72


def _header(text: str) -> str:
    return f"\n{_THICK_SEP}\n  {text}\n{_THICK_SEP}"


def _section(title: str) -> str:
    return f"\n{_SEPARATOR}\n  {title}\n{_SEPARATOR}"


def _print_evidence(ev) -> None:
    print(f"  Error Type    : {ev.error_type}")
    print(f"  Error Message : {ev.error_message}")
    print(f"  File          : {ev.file}:{ev.line}")
    if ev.function_name:
        print(f"  Function      : {ev.function_name}")
    if ev.relevant_code:
        print(f"  Relevant Code : {ev.relevant_code.strip()}")


def _print_result(result) -> None:
    status = "✅ SUCCESS" if result.success else "❌ FAILED"
    print(f"\n  Status : {status}")

    if not result.success:
        print(f"  Error  : {result.error}")
        return

    d = result.diagnosis
    p = result.patch

    print(f"\n  ── DIAGNOSIS ──────────────────────────────────────────────")
    print(f"  Root Cause    : {d.root_cause}")
    print(f"  Explanation   : {d.explanation}")
    print(f"  Affected File : {d.affected_file}:{d.affected_line}")
    print(f"  Confidence    : {d.confidence * 100:.0f}%")

    print(f"\n  ── PATCH ──────────────────────────────────────────────────")
    if p is None:
        print("  No patch returned.")
    elif p.is_empty or not p.patches:
        print(f"  No fix possible: {p.explanation}")
    else:
        print(f"  Patches       : {len(p.patches)}")
        for i, fp in enumerate(p.patches, 1):
            print(f"  [{i}] File        : {fp.file}")
            print(f"      Old Code    : {fp.old_code.strip()}")
            print(f"      New Code    : {fp.new_code.strip()}")
        print(f"  Explanation   : {p.explanation}")


def _print_json(result) -> None:
    """Print the full structured JSON output."""
    output = {
        "success": result.success,
        "ran_at": result.ran_at.isoformat(),
        "error": result.error,
        "diagnosis": result.diagnosis.model_dump() if result.diagnosis else None,
        "patch": (
            result.patch.model_dump(exclude={"is_empty"})
            if result.patch else None
        ),
    }
    print("\n  ── FULL JSON OUTPUT ────────────────────────────────────────")
    for line in json.dumps(output, indent=2).splitlines():
        print(f"  {line}")


# ============================================================================ #
# Runner                                                                         #
# ============================================================================ #

def run_scenario(engine: LLMEngine, evidence, scenario_name: str, index: int) -> bool:
    """Run one scenario and print a formatted report. Returns True on success."""
    print(_header(f"SCENARIO {index + 1}: {scenario_name.upper().replace('_', ' ')}"))

    print(_section("INPUT EVIDENCE"))
    _print_evidence(evidence)

    print(_section("LLM ENGINE RESULT"))
    start = time.monotonic()
    result = engine.run(evidence)
    elapsed = time.monotonic() - start

    _print_result(result)
    _print_json(result)

    print(f"\n  ⏱  Completed in {elapsed:.1f}s")
    return result.success


def main() -> None:
    # ------------------------------------------------------------------ #
    # Check API key before doing anything                                  #
    # ------------------------------------------------------------------ #
    if not os.environ.get("GROQ_API_KEY"):
        print(
            "\n⚠️  GROQ_API_KEY is not set.\n"
            "   Set it before running:\n"
            "     PowerShell : $env:GROQ_API_KEY = 'gsk_...'\n"
            "     bash       : export GROQ_API_KEY='gsk_...'\n"
        )
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Parse CLI arguments                                                  #
    # ------------------------------------------------------------------ #
    args = sys.argv[1:]

    if "--list" in args:
        print("\nAvailable scenarios:")
        for name in list_scenarios():
            print(f"  {name}")
        sys.exit(0)

    # Determine which scenarios to run
    if args:
        raw = args[0]
        try:
            key: str | int = int(raw)
        except ValueError:
            key = raw
        try:
            selected = [(key if isinstance(key, str) else list_scenarios()[key], get_scenario(key))]
        except (KeyError, IndexError) as exc:
            print(f"\n❌ {exc}")
            sys.exit(1)
    else:
        selected = list(zip(list_scenarios(), SCENARIOS))

    # ------------------------------------------------------------------ #
    # Build engine (one instance shared across all scenarios)              #
    # ------------------------------------------------------------------ #
    print(_thick := _THICK_SEP)
    print("  🔥 Phoenix LLM Engine — Smoke Test")
    print(f"  Scenarios to run: {len(selected)}")
    print(_thick)

    engine = LLMEngine()

    # ------------------------------------------------------------------ #
    # Run scenarios                                                         #
    # ------------------------------------------------------------------ #
    passed = 0
    failed = 0

    for i, (name, evidence) in enumerate(selected):
        success = run_scenario(engine, evidence, name, i)
        if success:
            passed += 1
        else:
            failed += 1

        # Brief pause between calls to avoid rate limiting
        if i < len(selected) - 1:
            time.sleep(1.5)

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    print(f"\n{_THICK_SEP}")
    print(f"  SMOKE TEST COMPLETE")
    print(f"  Passed : {passed}/{len(selected)}")
    if failed:
        print(f"  Failed : {failed}/{len(selected)}")
    print(_THICK_SEP)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
