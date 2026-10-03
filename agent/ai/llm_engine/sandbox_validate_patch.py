"""
Phoenix — Minimal isolated patch-validation sandbox (STAND-IN).

STATUS: Phoenix does NOT yet ship a sandbox component. The only existing
"validation" is `_validate_patch()` in patch.py, which is a *static* check
(old_code is a substring of relevant_code, non-empty). Nothing applies a
patch or runs tests. `future/code_agent/` defines interfaces only.

This script STANDS IN for the missing sandbox to answer one question:
is the LLM-generated single-file patch complete? It:

  1. Copies backend/ -> a temp sandbox dir (the REAL files are never touched).
  2. Applies the generated patch (old_code -> new_code) to the COPY only.
  3. Verifies the real production file was NOT modified.
  4. Runs the target pytest inside the sandbox.
  5. Reports PASS/FAIL + reason.

Usage:
  python -m agent.ai.llm_engine.sandbox_validate_patch [test_selector]

  test_selector defaults to:
    backend/tests/test_incident_severity_count.py::test_severity_filter_applies_to_total_count
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# --------------------------------------------------------------------------- #
# The generated patch (from the real Groq run)                                 #
# --------------------------------------------------------------------------- #
PATCH_FILE_REL = "backend/services/incident_service.py"
PATCH_OLD = "total = repo.count_incidents(service=service, status=status, resolved=resolved)"
PATCH_NEW = (
    "total = repo.count_incidents("
    "service=service, status=status, severity=severity, resolved=resolved)"
)

DEFAULT_TEST = (
    "backend/tests/test_incident_severity_count.py::"
    "test_severity_filter_applies_to_total_count"
)

# Workspace root = agent/ai/llm_engine/sandbox_validate_patch.py -> parents[3]
WORKSPACE = pathlib.Path(__file__).resolve().parents[3]
BACKEND_SRC = WORKSPACE / "backend"

_THICK = "=" * 78


def _find_line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line
    return "(line not found)"


def main() -> None:
    test_selector = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEST

    # ------------------------------------------------------------------ #
    # 1. Create an isolated sandbox and copy the backend into it          #
    # ------------------------------------------------------------------ #
    sandbox = pathlib.Path(tempfile.mkdtemp(prefix="phoenix_sandbox_"))

    shutil.copytree(
        BACKEND_SRC,
        sandbox / "backend",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    print(f"{_THICK}\n  SANDBOX ENVIRONMENT\n{_THICK}")
    print(f"  sandbox root : {sandbox}")
    print(f"  backend copy : {sandbox / 'backend'}")
    print(f"  real backend : {BACKEND_SRC}  (NOT modified)")

    # ------------------------------------------------------------------ #
    # 2. Apply the generated patch to the COPY only                       #
    # ------------------------------------------------------------------ #
    target = sandbox / PATCH_FILE_REL
    content = target.read_text(encoding="utf-8")
    occurrences = content.count(PATCH_OLD)
    if occurrences != 1:
        print(f"\n  ABORT: old_code found {occurrences} time(s) in copy (expected 1)")
        sys.exit(3)

    patched = content.replace(PATCH_OLD, PATCH_NEW, 1)
    target.write_text(patched, encoding="utf-8")

    before = _find_line(content, PATCH_OLD)
    after = _find_line(patched, PATCH_NEW)
    print(f"\n{_THICK}\n  PATCH APPLIED (to copy only)\n{_THICK}")
    print(f"  file     : {PATCH_FILE_REL}")
    print(f"  old line : {before.strip()}")
    print(f"  new line : {after.strip()}")

    # ------------------------------------------------------------------ #
    # 3. Verify the REAL production file was NOT changed                  #
    # ------------------------------------------------------------------ #
    real_content = (BACKEND_SRC / "services/incident_service.py").read_text(encoding="utf-8")
    real_touched = PATCH_NEW in real_content
    print(f"\n  REAL production file modified? : {real_touched}")
    if real_touched:
        print("  ERROR: real file was modified — aborting")
        sys.exit(4)

    # ------------------------------------------------------------------ #
    # 4. Run the target pytest inside the sandbox                         #
    # ------------------------------------------------------------------ #
    cmd = [sys.executable, "-m", "pytest", test_selector, "-v", "--no-header"]
    print(f"\n{_THICK}\n  PYTEST (run inside sandbox)\n{_THICK}")
    print(f"  cwd   : {sandbox}")
    print(f"  cmd   : {' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=str(sandbox),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout + proc.stderr).strip()
    print("\n" + output)

    # ------------------------------------------------------------------ #
    # 5. Report PASS/FAIL + reason                                        #
    # ------------------------------------------------------------------ #
    print(f"\n{_THICK}\n  RESULT\n{_THICK}")
    print(f"  returncode : {proc.returncode}")
    print(f"  outcome    : {'PASS' if proc.returncode == 0 else 'FAIL'}")

    if proc.returncode != 0:
        # Pull the most informative error line(s) out of the pytest output
        reason_lines = [
            ln for ln in output.splitlines()
            if ln.strip().startswith(("E   ", "E ", "Error", "TypeError", "AssertionError"))
        ]
        print(f"  reason     :")
        for ln in reason_lines[-6:]:
            print(f"    {ln.strip()}")

    print(f"\n  (sandbox kept at {sandbox} for inspection; real files untouched)")


if __name__ == "__main__":
    main()
