"""Local Docker analysis for connected repositories."""
from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import time
import uuid
from typing import Any

import requests

from agent.sandbox.project_detector import detect_project

logger = logging.getLogger(__name__)


def _generated_dockerfile(root: pathlib.Path) -> str:
    plan = detect_project(root)
    if plan.language == "javascript":
        return (
            "FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\n"
            "RUN npm ci --omit=dev || npm install --omit=dev\nCOPY . .\n"
            "EXPOSE 3000\nCMD [\"npm\", \"start\"]\n"
        )
    if (root / "pyproject.toml").exists():
        return (
            "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\n"
            "RUN pip install --no-cache-dir .\nEXPOSE 8000\n"
            "CMD [\"sh\", \"-c\", \"python -m uvicorn app.main:app --host 0.0.0.0 --port 8000\"]\n"
        )
    return (
        "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements*.txt ./\n"
        "RUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\n"
        "EXPOSE 8000\nCMD [\"sh\", \"-c\", \"python -m uvicorn app.main:app --host 0.0.0.0 --port 8000\"]\n"
    )


def analyze_repository(root: pathlib.Path, repository: str) -> dict[str, Any]:
    """Build and run a temporary image, returning only observed values."""
    dockerfile = next(root.rglob("Dockerfile"), None)
    generated = dockerfile is None
    if generated:
        dockerfile = root / "Dockerfile"
        dockerfile.write_text(_generated_dockerfile(root), encoding="utf-8")

    image = f"phoenix-analysis-{uuid.uuid4().hex[:12]}"
    container = f"phoenix-analysis-{uuid.uuid4().hex[:12]}"
    result: dict[str, Any] = {
        "repository": repository,
        "status": "failed",
        "dockerfile_present": not generated,
        "dockerfile_generated": generated,
        "language": detect_project(root).language,
        "image": image,
        "container": container,
    }
    try:
        build = subprocess.run(
            ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
            capture_output=True, text=True, timeout=300,
        )
        result["build"] = {"passed": build.returncode == 0, "stdout": build.stdout[-4000:], "stderr": build.stderr[-4000:]}
        if build.returncode:
            result["error"] = "Docker image build failed"
            return result
        run = subprocess.run(
            ["docker", "run", "-d", "--rm", "--label", "phoenix.analysis=true", "-P", "--name", container, image],
            capture_output=True, text=True, timeout=30,
        )
        if run.returncode:
            result["error"] = run.stderr[-2000:]
            return result
        result["container_id"] = run.stdout.strip()
        port = _published_port(container)
        health = _probe_health(port, 45)
        result["health"] = health
        result["status"] = "ready" if health["healthy"] else "failed"
        result["container_status"] = _command(
            ["docker", "inspect", "-f", "{{.State.Status}}", container]
        )
        result["logs"] = _command(["docker", "logs", "--tail", "200", container])
        result["resources"] = _resources(container)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True)
        subprocess.run(["docker", "rmi", "-f", image], capture_output=True, text=True)
        if generated and dockerfile:
            dockerfile.unlink(missing_ok=True)


def _published_port(container: str) -> int:
    inspect = _command(["docker", "port", container])
    for line in inspect.splitlines():
        if ":" in line:
            return int(line.rsplit(":", 1)[1])
    raise RuntimeError("Container did not publish a port")


def _probe_health(port: int, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    paths = ("/health", "/api/health", "/")
    last_error = ""
    while time.monotonic() < deadline:
        for path in paths:
            try:
                response = requests.get(f"http://127.0.0.1:{port}{path}", timeout=2)
                if response.status_code < 500:
                    return {"healthy": True, "path": path, "status_code": response.status_code}
                last_error = f"{path}: HTTP {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
        time.sleep(2)
    return {"healthy": False, "error": last_error}


def _resources(container: str) -> dict[str, Any]:
    raw = _command(["docker", "stats", "--no-stream", "--format", "{{json .}}", container])
    try:
        return json.loads(raw.splitlines()[0])
    except (ValueError, IndexError):
        return {"raw": raw}


def _command(command: list[str]) -> str:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return (proc.stdout or "").strip()
