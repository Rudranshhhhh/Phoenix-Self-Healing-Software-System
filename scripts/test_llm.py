"""Quick smoke-test: verify the LLM key + model work for a real diagnosis."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from agent.ai.llm_engine.client import GroqLLMClient
from agent.ai.llm_engine.diagnosis import EvidenceInput, generate_diagnosis

client = GroqLLMClient()
print("Model:  ", client.model)
print("Key:    ", os.environ.get("GROQ_API_KEY", "")[:16] + "...")

evidence = EvidenceInput(
    error_type="TypeError",
    error_message="Type string is not assignable to type number",
    file="src/phoenix-bug.ts",
    line=7,
    relevant_code='export const buggyValue: number = "hello world";',
    stack_trace="src/phoenix-bug.ts(7,14): error TS2322: Type 'string' is not assignable to type 'number'.",
    extra_context={"source": "github_ci", "stage": "typecheck"},
)

print("Running diagnosis...")
result = generate_diagnosis(evidence, client)
if result:
    print("root_cause:", result.root_cause[:120])
    print("confidence:", result.confidence)
    print("\nSTATUS: LLM DIAGNOSIS WORKING ✓")
else:
    print("\nSTATUS: FAILED — LLM returned None")
    sys.exit(1)
