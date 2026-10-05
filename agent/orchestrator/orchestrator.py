"""Runtime -> LLM -> sandbox -> phoenix-api, for one project folder."""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .evidence import build_evidence, split_error
from .ingest_client import IngestClient
from .workspace import create_workspace

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class RunResult:
    status: str  # no_failure | failed | rejected | validated | pr_opened
    agent_id: str = ""
    dashboard_id: str = ""
    workspace: Optional[Path] = None
    message: str = ""


class _Stop(Exception):
    """Ends the run early with a 'failed' event."""


@contextlib.contextmanager
def _without_github_env():
    """The sandbox falls back to these env vars; keep them out so nothing is pushed or opened."""
    saved = {k: os.environ.pop(k) for k in ("GITHUB_TOKEN", "GITHUB_REPO") if k in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def _default_monitor(project_dir: Path, timeout: float) -> Any:
    from agent.runtime.project_monitor import monitor_project

    return monitor_project(project_dir, timeout=timeout)


def _default_engine() -> Any:
    from agent.ai.llm_engine import LLMEngine

    return LLMEngine()


def _default_pipeline(run_lint: bool) -> Any:
    from agent.sandbox.models import SandboxConfig
    from agent.sandbox.pipeline import SandboxPipeline

    config = SandboxConfig(
        run_lint=run_lint,
        run_tests=True,
        run_docker=False,  # the runtime already ran it in Docker
        lint_targets=["."],
        test_paths=["."],
    )
    return SandboxPipeline(config=config, github_repo="", github_token="")


class Orchestrator:
    def __init__(
        self,
        ingest: Optional[IngestClient] = None,
        monitor: Optional[Callable[[Path, float], Any]] = None,
        engine_factory: Optional[Callable[[], Any]] = None,
        pipeline_factory: Optional[Callable[[bool], Any]] = None,
        workspaces_root: Optional[Path] = None,
        container_workdir: str = "/app",
        run_lint: bool = True,
        timeout: float = 60.0,
    ) -> None:
        self.ingest = ingest or IngestClient()
        self.monitor = monitor or _default_monitor
        self.engine_factory = engine_factory or _default_engine
        self.pipeline_factory = pipeline_factory or _default_pipeline
        self.workspaces_root = workspaces_root or REPO_ROOT / ".phoenix" / "workspaces"
        self.container_workdir = container_workdir
        self.run_lint = run_lint
        self.timeout = timeout

    def run(self, project_dir: Path | str) -> RunResult:
        project_dir = Path(project_dir).resolve()
        log.info("Running %s in Docker and watching for a crash", project_dir)
        report = self.monitor(project_dir, self.timeout)
        if report is None:
            return RunResult("no_failure", message="No failure detected before the timeout.")

        agent_id = str(uuid.uuid4())
        error_type, message = split_error(report.error)
        response = self.ingest.send(
            agent_id,
            "detected",
            source={"type": "docker_runtime", "container": report.container_name},
            error={"exception_type": error_type, "message": message, "stack_trace": report.stack_trace},
            message=f"Runtime caught {error_type} in container {report.container_name}",
        )
        dashboard_id = (response or {}).get("id") or f"local-{agent_id[:8]}"
        result = RunResult("failed", agent_id, dashboard_id)
        try:
            return self._heal(report, project_dir, result)
        except _Stop as stop:
            result.message = str(stop)
        except Exception as exc:  # the dashboard must always hear how it ended
            log.exception("Orchestrator error")
            result.message = f"Orchestrator error: {exc}"
        self.ingest.send(agent_id, "failed", message=result.message)
        return result

    def _heal(self, report: Any, project_dir: Path, result: RunResult) -> RunResult:
        agent_id = result.agent_id
        evidence = build_evidence(report, project_dir, self.container_workdir)
        self.ingest.send(
            agent_id, "diagnosing", message=f"Reading {evidence['file']} line {evidence['line']} and asking the LLM"
        )

        llm = self.engine_factory().run(evidence)
        if not llm.success:
            raise _Stop(f"LLM error: {llm.error}")
        if llm.patch is None or llm.patch.is_empty:
            raise _Stop("The LLM returned no patch")

        d = llm.diagnosis
        self.ingest.send(
            agent_id,
            "fix_proposed",
            diagnosis=None
            if d is None
            else {
                "root_cause": d.root_cause,
                "explanation": d.explanation,
                "affected_file": d.affected_file,
                "affected_line": d.affected_line,
                "confidence": d.confidence,
            },
            patch={
                "explanation": llm.patch.explanation,
                "patches": [
                    {"file": p.file, "old_code": p.old_code, "new_code": p.new_code} for p in llm.patch.patches
                ],
            },
        )

        workspace = create_workspace(project_dir, self.workspaces_root, result.dashboard_id)
        result.workspace = workspace
        self.ingest.send(agent_id, "validating", message="Testing the patch in a sandbox copy")
        with _without_github_env():
            outcome = self.pipeline_factory(self.run_lint).run(
                incident_id=result.dashboard_id, repo_path=workspace, llm_result=llm
            )

        v = outcome.validation
        if v is None:
            raise _Stop(outcome.error or "The sandbox stopped before validation")
        validation = {
            "validated": v.validated,
            "reason": v.reason,
            "test_stdout": v.test_stdout,
            "test_stderr": v.test_stderr,
            "duration_seconds": v.duration_seconds,
            "completed_at": v.completed_at.isoformat() if v.completed_at else None,
            "original_failure_resolved": v.original_failure_resolved,
        }
        if not v.validated:
            self.ingest.send(agent_id, "rejected", validation=validation, message=v.reason or "Patch rejected")
            result.status, result.message = "rejected", v.reason
            return result

        branch = (
            outcome.git.branch_name
            if outcome.git and outcome.git.branch_name
            else f"phoenix/fix/{result.dashboard_id}"
        )
        self.ingest.send(
            agent_id,
            "validated",
            validation=validation,
            message=f"Sandbox passed. Fix committed on {branch} in a local workspace (not pushed).",
        )
        result.status, result.message = "validated", f"Fix committed on {branch} in {workspace}"

        pr = outcome.pull_request
        if pr is not None and pr.success and pr.pr_url:
            self.ingest.send(
                agent_id,
                "pr_opened",
                pull_request={"pr_number": pr.pr_number, "pr_url": pr.pr_url, "head_branch": pr.head_branch},
            )
            result.status = "pr_opened"
        return result
