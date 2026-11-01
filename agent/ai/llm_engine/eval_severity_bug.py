"""
Phoenix LLM Engine — Evaluation harness for the severity-count bug (STAGE 1)

Runs the existing LLMEngine against the real severity-count evidence N times
and counts how many produced the COMPLETE, regression-verified two-file fix.

Correctness is NOT "the engine returned success" — a one-file patch can pass
the engine's own validation but still be incomplete. A run counts as CORRECT
only when applying ALL generated patches to an ISOLATED COPY of the backend
makes the regression test
    backend/tests/test_incident_severity_count.py
pass (i.e. both previously-failing and existing tests go green).

Counts tracked: correct, failed requests (API failures), incorrect patches,
current streak, and maximum consecutive correct fixes.

Modes:
  - real (default): uses GroqLLMClient (requires GROQ_API_KEY).
  - --mock         : uses MockLLMClient. Mock results are NEVER counted as real
                     Groq results (the summary records mode="mock").
  - --fallback    : on an API failure, the verified fallback (fallback_patch) is
                     sandbox-verified and reported, but it is NEVER counted as a
                     correct LLM generation.

The harness never applies patches to the team's working tree — it copies
backend/ to a throwaway temp dir.

Usage:
  python -m agent.ai.llm_engine.eval_severity_bug                 # 10 real runs
  python -m agent.ai.llm_engine.eval_severity_bug --runs 15
  python -m agent.ai.llm_engine.eval_severity_bug --mock          # offline check
  python -m agent.ai.llm_engine.eval_severity_bug --fallback
  python -m agent.ai.llm_engine.eval_severity_bug --out results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phoenix.eval_severity_bug")

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.engine import LLMEngine
from agent.ai.llm_engine.mock_client import MockLLMClient
from agent.ai.llm_engine.patch import FilePatch
from agent.ai.llm_engine.run_severity_bug import build_evidence

WORKSPACE = pathlib.Path(__file__).resolve().parents[3]
BACKEND_SRC = WORKSPACE / "backend"
DEFAULT_TEST = "backend/tests/test_incident_severity_count.py"
DEFAULT_RUNS = 10
STREAK_THRESHOLD = 3

_THICK = "=" * 78


# ============================================================================ #
# Isolated sandbox verification (applies patches to a temp copy, runs pytest)    #
# ============================================================================ #

def verify_patches_in_sandbox(
    patches: list[FilePatch],
    test_selector: str = DEFAULT_TEST,
) -> tuple[bool, str]:
    """
    Apply every patch to an ISOLATED COPY of backend/ and run the regression
    test there. Returns (passed, detail). Never touches the real working tree.

    A patch is applied via content.replace(old_code, new_code, 1). If any
    old_code is not a substring of its target file, the apply fails and the
    whole patch set is reported as not-passing.
    """
    sandbox = pathlib.Path(tempfile.mkdtemp(prefix="phoenix_eval_"))
    try:
        shutil.copytree(
            BACKEND_SRC,
            sandbox / "backend",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

        for fp in patches:
            target = sandbox / fp.file
            if not target.exists():
                return False, f"file not found in sandbox copy: {fp.file}"
            content = target.read_text(encoding="utf-8")
            if fp.old_code not in content:
                return False, f"old_code not found in {fp.file}: {fp.old_code!r}"
            target.write_text(content.replace(fp.old_code, fp.new_code, 1), encoding="utf-8")

        cmd = [sys.executable, "-m", "pytest", test_selector, "-q", "--no-header"]
        proc = subprocess.run(cmd, cwd=str(sandbox), capture_output=True, text=True)
        detail = (proc.stdout + proc.stderr).strip()
        return (proc.returncode == 0, detail)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


# ============================================================================ #
# Pure evaluation loop                                                           #
# ============================================================================ #

# A sandbox verifier takes a list of FilePatch and returns (passed, detail).
SandboxVerifier = Callable[[list[FilePatch]], tuple[bool, str]]


class _RecordingClient:
    """Wraps a client to record whether each complete() call returned content.

    This lets the harness distinguish a transport/API failure (no response at
    all -> the client returned None) from a patch-generation/validation failure
    (a response came back but was malformed or rejected). It does not change
    the client's behaviour — it only observes it.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[bool] = []  # True = returned content (not None)

    @property
    def model(self) -> str:
        return getattr(self._inner, "model", "recorded")

    def complete(self, **kwargs):
        r = self._inner.complete(**kwargs)
        self.calls.append(r is not None)
        return r


def _categorize_failure(run_calls: list[bool]) -> str:
    """Map the observed client calls during a failed run to a failure category.

    - API_FAILURE       : the failing stage's client call returned no response.
    - DIAGNOSIS_FAILURE : the diagnosis call returned content but was unparseable.
    - PATCH_FAILURE     : the patch call returned content but was malformed or
                          failed validation (patch-generation/validation failure).
    """
    if not run_calls:
        return "API_FAILURE"
    if len(run_calls) == 1:
        # Only the diagnosis call happened (engine aborts before patching).
        return "API_FAILURE" if not run_calls[0] else "DIAGNOSIS_FAILURE"
    # Diagnosis succeeded; the patch stage failed.
    return "API_FAILURE" if not run_calls[-1] else "PATCH_FAILURE"


def evaluate(
    client,
    evidence,
    runs: int,
    sandbox_verify: SandboxVerifier,
    use_fallback: bool = False,
    fallback=None,
    mode: str = "real",
) -> dict:
    """
    Run the LLMEngine `runs` times and score correctness via the sandbox.

    Returns a machine-readable summary dict (also written to JSON by main()).

    Outcome categories:
      CORRECT            — an LLM-generated patch set passes the sandbox regression.
      INCORRECT          — an LLM-generated patch set was produced but the sandbox
                           regression fails (incomplete or wrong fix).
      API_FAILURE        — the LLM call returned no response (transport/rate-limit/
                           timeout/auth). NOT a patch-quality problem.
      DIAGNOSIS_FAILURE  — a diagnosis response came back but was unparseable.
      PATCH_FAILURE      — a patch response came back but was malformed or failed
                           validation (patch-generation/validation failure).
      HARNESS_ERROR      — an unexpected exception during a run.

    Streak rule: only an LLM-generated, sandbox-verified CORRECT run increments
    the streak. Failures and incorrect patches reset it. Fallback use is recorded
    but never counts as a correct LLM generation.

    Mock vs real: `correct` is the count within this evaluation. `real_correct` is
    only non-zero in real mode; `mock_correct` is only non-zero in mock mode — so a
    mock run can never be read as a real Groq success.
    """
    recording = _RecordingClient(client)
    engine = LLMEngine(client=recording)
    records: list[dict] = []
    correct = 0
    api_failures = 0
    diagnosis_failures = 0
    patch_failures = 0
    incorrect = 0
    current_streak = 0
    max_streak = 0
    fallback_used = 0
    fallback_verified = 0

    for i in range(1, runs + 1):
        calls_before = len(recording.calls)
        rec: dict = {"run": i, "mode": mode}
        try:
            result = engine.run(evidence)
        except Exception as exc:  # harness must never abort on one run
            rec.update(outcome="HARNESS_ERROR", error=str(exc))
            records.append(rec)
            current_streak = 0
            continue

        run_calls = recording.calls[calls_before:]
        rec["success"] = result.success
        rec["error"] = result.error
        if result.diagnosis:
            rec["diagnosis_root_cause"] = result.diagnosis.root_cause

        # --- Failure: no usable patch (API error / malformed / validation) -- #
        if (not result.success) or result.patch is None or result.patch.is_empty:
            category = _categorize_failure(run_calls)
            rec["outcome"] = category
            if category == "API_FAILURE":
                api_failures += 1
            elif category == "DIAGNOSIS_FAILURE":
                diagnosis_failures += 1
            else:  # PATCH_FAILURE
                patch_failures += 1
            current_streak = 0
            if use_fallback and fallback is not None:
                rec["used_fallback"] = True
                fallback_used += 1
                passed, detail = sandbox_verify(fallback.patches)
                rec["fallback_verified"] = passed
                rec["fallback_detail"] = "passed" if passed else (detail or "")[-600:]
                if passed:
                    fallback_verified += 1
            records.append(rec)
            continue

        # --- Success: a non-empty patch was produced -> sandbox-verify it ---- #
        rec["patch_count"] = len(result.patch.patches)
        rec["files_touched"] = [fp.file for fp in result.patch.patches]
        passed, detail = sandbox_verify(result.patch.patches)
        rec["sandbox_passed"] = passed
        if passed:
            rec["outcome"] = "CORRECT"
            correct += 1
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            rec["outcome"] = "INCORRECT"
            rec["sandbox_detail"] = (detail or "")[-600:]
            incorrect += 1
            current_streak = 0
        records.append(rec)

    return {
        "mode": mode,
        "runs": runs,
        "correct": correct,
        "real_correct": correct if mode == "real" else 0,
        "mock_correct": correct if mode == "mock" else 0,
        "api_failures": api_failures,
        "diagnosis_failures": diagnosis_failures,
        "patch_failures": patch_failures,
        "incorrect": incorrect,
        "current_streak": current_streak,
        "max_streak": max_streak,
        "fallback_used": fallback_used,
        "fallback_verified": fallback_verified,
        "records": records,
    }


# ============================================================================ #
# CLI                                                                            #
# ============================================================================ #

def _print_summary(s: dict) -> None:
    print(f"\n{_THICK}\n  EVALUATION SUMMARY\n{_THICK}")
    print(f"  mode                : {s['mode']}")
    if s["mode"] == "mock":
        print("  NOTE                : MOCK results — NOT real Groq results.")
    print(f"  runs                : {s['runs']}")
    print(f"  correct             : {s['correct']}  (real_correct={s['real_correct']}, mock_correct={s['mock_correct']})")
    print(f"  api_failures        : {s['api_failures']}  (no response from the LLM)")
    print(f"  diagnosis_failures  : {s['diagnosis_failures']}  (response unparseable)")
    print(f"  patch_failures      : {s['patch_failures']}  (malformed or validation-rejected)")
    print(f"  incorrect           : {s['incorrect']}  (patch produced, sandbox failed)")
    print(f"  current_streak      : {s['current_streak']}")
    print(f"  max_streak          : {s['max_streak']}")
    print(f"  fallback_used       : {s['fallback_used']}")
    print(f"  fallback_verified   : {s['fallback_verified']}")
    # Per-run verdict line
    print("\n  per-run:")
    for r in s["records"]:
        extra = ""
        if r.get("used_fallback"):
            extra = f" [fallback used, verified={r.get('fallback_verified')}]"
        print(
            f"    run {r['run']:>2} [{r['mode']}] -> {r.get('outcome', '?')} "
            f"(files={r.get('files_touched')}){extra}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phoenix LLM severity-bug evaluation harness")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help=f"number of runs (default {DEFAULT_RUNS})")
    parser.add_argument("--mock", action="store_true", help="use MockLLMClient (offline; never counted as real)")
    parser.add_argument("--fallback", action="store_true", help="use verified fallback on API failure (not counted as LLM success)")
    parser.add_argument("--out", default="eval_results.json", help="path to write machine-readable JSON results")
    parser.add_argument("--streak-threshold", type=int, default=STREAK_THRESHOLD, help="exit 0 in real mode only if max_streak >= this (default 3)")
    args = parser.parse_args()

    evidence = build_evidence()

    if args.mock:
        print(f"\n{_THICK}\n  *** MOCK MODE (MockLLMClient) — NOT real Groq results ***\n{_THICK}")
        client = MockLLMClient()
        mode = "mock"
    else:
        if not os.environ.get("GROQ_API_KEY"):
            print(
                f"\n{_THICK}\n  GROQ_API_KEY is not set — cannot run real Groq evaluation.\n"
                f"  Set it and re-run:\n"
                f"     PowerShell : $env:GROQ_API_KEY = 'gsk_...'\n"
                f"     then       : python -m agent.ai.llm_engine.eval_severity_bug\n"
                f"  Or run an offline plumbing check with --mock.\n{_THICK}"
            )
            sys.exit(2)
        print(f"\n{_THICK}\n  REAL GROQ EVALUATION (GroqLLMClient)\n{_THICK}")
        client = GroqLLMClient()
        mode = "real"

    fallback = None
    if args.fallback:
        from agent.ai.llm_engine.fallback_patch import build_fallback_patch
        fallback = build_fallback_patch()
        logger.info("Fallback enabled: verified fixture loaded (NOT counted as LLM success).")

    summary = evaluate(
        client=client,
        evidence=evidence,
        runs=args.runs,
        sandbox_verify=verify_patches_in_sandbox,
        use_fallback=args.fallback,
        fallback=fallback,
        mode=mode,
    )

    _print_summary(summary)

    out_path = pathlib.Path(args.out)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n  results written to: {out_path.resolve()}")

    if mode == "real":
        if summary["max_streak"] >= args.streak_threshold:
            print(f"\n  [PASS] max_streak {summary['max_streak']} >= {args.streak_threshold}")
            sys.exit(0)
        print(f"\n  [NOT YET] max_streak {summary['max_streak']} < {args.streak_threshold} (tune prompts next)")
        sys.exit(1)
    # mock mode is a plumbing check — success means the harness ran cleanly.
    print("\n  [OK] mock harness ran cleanly (mock results are not real Groq results).")
    sys.exit(0)


if __name__ == "__main__":
    main()
