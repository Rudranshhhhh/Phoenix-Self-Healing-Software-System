"""Test diagnosis + patch generation end-to-end with the real file content."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.diagnosis import EvidenceInput, generate_diagnosis
from agent.ai.llm_engine.patch import generate_patch

client = GroqLLMClient()
print("Model:", client.model)

# Simulate exactly what the worker sees for the portfolio TypeScript bug
evidence = EvidenceInput(
    error_type="TSError",
    error_message="Type 'string' is not assignable to type 'number'",
    file="src/phoenix-bug.ts",
    line=4,
    relevant_code="""\
// Phoenix self-healing test — deliberate type errors (v3)
// Phoenix will clone this repo, read this file, and fix these errors.

export const buggyValue: number = "hello world";

export function brokenAdd(a: number, b: number): string {
  return a + b;
}

export const anotherBug: boolean = 42;""",
    stack_trace=(
        "src/phoenix-bug.ts(4,14): error TS2322: "
        "Type 'string' is not assignable to type 'number'.\n"
        "src/phoenix-bug.ts(10,14): error TS2322: "
        "Type 'number' is not assignable to type 'boolean'."
    ),
    extra_context={"source": "github_ci", "stage": "typecheck", "repository": "Rudranshhhhh/Rudransh-portfolio"},
)

print("\nStep 1: Diagnosis...")
diagnosis = generate_diagnosis(evidence, client)
if not diagnosis:
    print("FAILED: diagnosis returned None")
    sys.exit(1)
print("  root_cause:", diagnosis.root_cause[:100])
print("  confidence:", diagnosis.confidence)

print("\nStep 2: Patch generation...")
patch = generate_patch(evidence, diagnosis, client)
if not patch or patch.is_empty:
    print("FAILED: patch is empty or None")
    sys.exit(1)

print("  patches:", len(patch.patches))
for p in patch.patches:
    print(f"  file={p.file}")
    print(f"  old_code={p.old_code[:60]!r}")
    print(f"  new_code={p.new_code[:60]!r}")
print("  explanation:", patch.explanation[:100])
print("\nSTATUS: FULL PIPELINE WORKING ✓")
