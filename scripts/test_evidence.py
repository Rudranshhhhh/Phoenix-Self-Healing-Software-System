"""Test that evidence extraction correctly parses the one-line tsc output."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "phoenix-api"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
from unittest.mock import MagicMock
for m in ['agent.sandbox','agent.sandbox.models']:
    sys.modules[m] = MagicMock()

from app.evidence import extract_evidence_from_ci_payload, enrich_evidence_from_repository, _parse_ci_logs
import pathlib

# Exact logs from INC-017 (all on one line because the workflow used tr '\n' ' ')
LOGS = (
    " > rudransh-os@1.0.0 typecheck > tsc --noEmit  "
    "src/phoenix-bug.ts(5,14): error TS2322: Type 'string' is not assignable to type 'number'. "
    "src/phoenix-bug.ts(8,3): error TS2322: Type 'number' is not assignable to type 'string'. "
    "src/phoenix-bug.ts(11,14): error TS2322: Type 'number' is not assignable to type 'boolean'."
)

print("=== _parse_ci_logs ===")
error_type, error_message, file_hint, line_hint = _parse_ci_logs(LOGS, "typecheck")
print(f"error_type:    {error_type!r}")
print(f"error_message: {error_message!r}")
print(f"file_hint:     {file_hint!r}")
print(f"line_hint:     {line_hint!r}")
print()

payload = {
    "source": "github_ci",
    "repository": "Rudranshhhhh/Rudransh-portfolio",
    "commit": "d82b4d2821c6",
    "branch": "main",
    "stage": "typecheck",
    "logs": LOGS,
}

print("=== extract_evidence_from_ci_payload ===")
ev = extract_evidence_from_ci_payload(payload)
print(f"file:          {ev.file!r}")
print(f"line:          {ev.line}")
print(f"relevant_code: {repr(ev.relevant_code)[:80] if ev.relevant_code else 'None'}")
print()

print("=== enrich_evidence_from_repository ===")
repo_path = pathlib.Path("C:/raghav/portfolio/Rudransh-portfolio")
ev2 = enrich_evidence_from_repository(ev, repo_path)
print(f"file:          {ev2.file!r}")
print(f"line:          {ev2.line}")
print(f"relevant_code: {'YES (' + str(len(ev2.relevant_code)) + ' chars)' if ev2.relevant_code else 'NONE — this is the bug'}")
if ev2.relevant_code:
    print()
    print("First 200 chars of relevant_code:")
    print(ev2.relevant_code[:200])
