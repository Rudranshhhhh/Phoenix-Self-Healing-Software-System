"""
Phoenix LLM Engine

Public API for the code-level diagnosis and patch generation module.

This package receives structured evidence about a code failure (error type,
stack trace, source snippet, file/line) and returns a structured response
containing a diagnosis and a proposed code patch — both validated by Pydantic.

Typical usage
-------------
    from agent.ai.llm_engine import LLMEngine, EvidenceInput, LLMEngineResult

    engine = LLMEngine()
    result: LLMEngineResult = engine.run(
        EvidenceInput(
            error_type="TypeError",
            error_message="unsupported operand type(s) for +: 'int' and 'str'",
            file="backend/app/example.py",
            line=42,
            relevant_code="score = mood_score + mood",
            stack_trace="...",
        )
    )
    print(result.diagnosis.root_cause)
    print(result.patch.new_code)

Boundary contract
-----------------
- Input:  EvidenceInput  (Pydantic model, defined in diagnosis.py)
- Output: LLMEngineResult (Pydantic model, defined in engine.py)
- The engine NEVER modifies source files.
- The patch is a proposal only; applying it is the responsibility of the
  downstream Sandbox / Validation component.
"""
from agent.ai.llm_engine.engine import LLMEngine, LLMEngineResult
from agent.ai.llm_engine.diagnosis import DiagnosisResult, EvidenceInput
from agent.ai.llm_engine.patch import PatchResult, FilePatch
from agent.ai.llm_engine.client import GroqLLMClient

__all__ = [
    "LLMEngine",
    "LLMEngineResult",
    "EvidenceInput",
    "DiagnosisResult",
    "PatchResult",
    "FilePatch",
    "GroqLLMClient",
]
