"""Show the raw LLM response for the patch prompt to debug why it returns empty."""
import sys, os, logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.diagnosis import EvidenceInput, generate_diagnosis, DiagnosisResult
from agent.ai.llm_engine.prompts import SYSTEM_PROMPT, build_patch_prompt
from agent.ai.llm_engine.patch import generate_patch, _extract_json

# Exact logs from INC-017
LOGS = (
    " > rudransh-os@1.0.0 typecheck > tsc --noEmit  "
    "src/phoenix-bug.ts(5,14): error TS2322: Type 'string' is not assignable to type 'number'. "
    "src/phoenix-bug.ts(8,3): error TS2322: Type 'number' is not assignable to type 'string'. "
    "src/phoenix-bug.ts(11,14): error TS2322: Type 'number' is not assignable to type 'boolean'."
)

SOURCE = """\
// Phoenix self-healing test — deliberate type errors
// Phoenix will clone this repo, read this file, and fix these errors.

export const buggyValue: number = "hello world";

export function brokenAdd(a: number, b: number): string {
  return a + b;
}

export const anotherBug: boolean = 42;"""

evidence = EvidenceInput(
    error_type="TSError",
    error_message="Type 'string' is not assignable to type 'number'",
    file="src/phoenix-bug.ts",
    line=5,
    relevant_code=SOURCE,
    stack_trace=LOGS,
    extra_context={"source": "github_ci", "stage": "typecheck"},
)

client = GroqLLMClient()
print("=== Step 1: Diagnosis ===")
diagnosis = generate_diagnosis(evidence, client)
print("root_cause:", diagnosis.root_cause[:100] if diagnosis else "FAILED")
print()

print("=== Step 2: Raw patch response ===")
from agent.ai.llm_engine.prompts import build_patch_prompt, SYSTEM_PROMPT
prompt = build_patch_prompt(evidence, diagnosis)
raw = client.complete(user_prompt=prompt, system_prompt=SYSTEM_PROMPT, max_tokens=900, temperature=0.1)
print("RAW RESPONSE:")
print(raw)
print()

print("=== Step 3: Parse attempt ===")
try:
    data = _extract_json(raw)
    print("Parsed JSON:", data)
    print("patches:", data.get("patches"))
except Exception as e:
    print("JSON parse error:", e)

print()
print("=== Step 4: Full generate_patch ===")
patch = generate_patch(evidence, diagnosis, client)
if patch and not patch.is_empty:
    print("SUCCESS:", len(patch.patches), "patches")
    for p in patch.patches:
        print(f"  file={p.file}")
        print(f"  old={p.old_code[:50]!r}")
        print(f"  new={p.new_code[:50]!r}")
else:
    print("FAILED: patch is empty or None")
