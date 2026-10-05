"""
Phoenix Sandbox — Patch Validation + Git Fix Pipeline

Public API for Person 4's module.

Typical usage (called by the Phoenix orchestrator or Person 5):
-----------------------------------------------------------------
    from agent.sandbox import SandboxPipeline, PatchOutcome

    pipeline = SandboxPipeline()
    outcome: PatchOutcome = pipeline.run(
        incident_id="INC-007",
        repo_path="/path/to/repo",        # local checkout root
        llm_result=llm_engine_result,     # LLMEngineResult from LLMEngine.run()
    )
    if outcome.validated:
        print(outcome.pull_request_url)   # PR is ready for review
    else:
        print(outcome.validation.reason)  # why it was rejected

Design principles
-----------------
- The patch NEVER touches the production repository directly.
- A temporary copy is created for every incident.
- Docker is used as the isolated validation environment.
- Validation must PASS before any branch, commit, or PR is created.
- Cleanup is guaranteed via context managers even on failure.
- GitHub credentials are never embedded in commits or logs.
"""
from agent.sandbox.models import (
    SandboxConfig,
    ValidationResult,
    PatchOutcome,
    DockerResult,
    GitResult,
    PRResult,
)
from agent.sandbox.pipeline import SandboxPipeline
from agent.sandbox.code_patch_engine import CodePatchEngine

__all__ = [
    "SandboxPipeline",
    "CodePatchEngine",
    "SandboxConfig",
    "ValidationResult",
    "PatchOutcome",
    "DockerResult",
    "GitResult",
    "PRResult",
]
