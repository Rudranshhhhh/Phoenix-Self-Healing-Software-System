"""Poll Render for queued incidents and process them locally with Docker."""
from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from pathlib import Path

import requests

from agent.ai.llm_engine import LLMEngine
from agent.sandbox import SandboxPipeline
from agent.sandbox.models import SandboxConfig
from agent.sandbox.repository_workspace import cloned_repository
from agent.worker.repository_analysis import analyze_repository

logger = logging.getLogger(__name__)
_API_SOURCE = Path(__file__).resolve().parents[2] / "phoenix-api"
if str(_API_SOURCE) not in sys.path:
    sys.path.insert(0, str(_API_SOURCE))


class AgentWorker:
    def __init__(self) -> None:
        self.api_url = os.environ["PHOENIX_API_URL"].rstrip("/")
        self.agent_token = os.environ["PHOENIX_AGENT_TOKEN"]
        self.worker_id = os.environ.get("PHOENIX_AGENT_ID", f"worker-{uuid.uuid4().hex[:8]}")
        self.poll_seconds = float(os.environ.get("PHOENIX_AGENT_POLL_SECONDS", "5"))
        self.session = requests.Session()

    def run_forever(self) -> None:
        while True:
            try:
                if not self.process_one():
                    time.sleep(self.poll_seconds)
            except Exception:
                logger.exception("Agent worker iteration failed")
                time.sleep(self.poll_seconds)

    def process_one(self) -> bool:
        if self.process_analysis():
            return True
        response = self.session.post(
            f"{self.api_url}/api/agent/jobs/claim",
            params={"worker_id": self.worker_id},
            headers={"X-Phoenix-Agent-Token": self.agent_token},
            timeout=30,
        )
        response.raise_for_status()
        job = response.json().get("job")
        if not job:
            return False

        incident = job["incident"]
        repository = job["repository"]
        token = job["github_token"]
        incident_id = incident["incident_id"]
        try:
            result = self._process(incident, repository, token)
        except Exception as exc:
            logger.exception("Incident %s failed in worker", incident_id)
            result = {"status": "agent_failed", "message": str(exc)}
        self.session.post(
            f"{self.api_url}/api/agent/jobs/{incident_id}/result",
            params={"worker_id": self.worker_id},
            headers={"X-Phoenix-Agent-Token": self.agent_token},
            json=result,
            timeout=30,
        ).raise_for_status()
        return True

    def process_analysis(self) -> bool:
        response = self.session.post(
            f"{self.api_url}/api/agent/analysis/claim",
            params={"worker_id": self.worker_id},
            headers={"X-Phoenix-Agent-Token": self.agent_token},
            timeout=30,
        )
        response.raise_for_status()
        job = response.json().get("job")
        if not job:
            return False
        repository = job["repository"]
        token = job["github_token"]
        result: dict
        try:
            with cloned_repository(repository, token, job["default_branch"], "") as root:
                result = analyze_repository(root, repository)
        except Exception as exc:
            result = {"repository": repository, "status": "failed", "error": str(exc)}
        result.update({"repository": repository, "worker_id": self.worker_id})
        self.session.post(
            f"{self.api_url}/api/agent/analysis/result",
            headers={"X-Phoenix-Agent-Token": self.agent_token},
            json=result,
            timeout=30,
        ).raise_for_status()
        return True

    def _process(self, incident: dict, repository: dict, token: str) -> dict:
        incident_id = incident["incident_id"]
        payload = incident.get("payload", {})
        from app.evidence import (
            enrich_evidence_from_repository,
            extract_evidence_from_ci_payload,
            extract_evidence_from_docker_incident,
        )

        with cloned_repository(
            repository["fullName"],
            token,
            incident.get("branch") or repository["defaultBranch"],
            incident.get("commit", ""),
        ) as repo_path:
            if incident["source"] == "github_ci":
                evidence = extract_evidence_from_ci_payload(payload)
            else:
                evidence = extract_evidence_from_docker_incident(payload)
            if evidence is None:
                raise RuntimeError("Could not build incident evidence")
            evidence = enrich_evidence_from_repository(evidence, repo_path)
            llm_result = LLMEngine().run(evidence)
            pipeline = SandboxPipeline(
                config=SandboxConfig(
                    sandbox_base_dir="",
                    run_lint=True,
                    run_tests=True,
                    run_docker=True,
                    skip_docker_if_unavailable=False,
                ),
                github_repo=repository["fullName"],
                base_branch=repository["defaultBranch"],
                github_token=token,
            )
            outcome = pipeline.run(
                incident_id=incident_id,
                repo_path=repo_path,
                llm_result=llm_result,
            )
            validation = outcome.validation.model_dump() if outcome.validation else None
            result = {
                "status": (
                    "pr_opened"
                    if outcome.pull_request_url
                    else "validated"
                    if outcome.validated
                    else "rejected"
                ),
                "message": outcome.summary(),
                "validation": validation,
                "evidence": llm_result.evidence.model_dump(),
                "diagnosis": llm_result.diagnosis.model_dump()
                if llm_result.diagnosis
                else None,
                "patch": llm_result.patch.model_dump() if llm_result.patch else None,
                "git": outcome.git.model_dump() if outcome.git else None,
                "pull_request": outcome.pull_request.model_dump()
                if outcome.pull_request
                else None,
            }
            return result


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    AgentWorker().run_forever()
