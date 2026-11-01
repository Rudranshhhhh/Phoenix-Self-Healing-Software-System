"""Local Docker analysis for connected repositories."""
from __future__ import annotations

import json
import logging
import pathlib
import re
import subprocess
import time
import uuid
from typing import Any

import requests

from agent.sandbox.project_detector import detect_project

logger = logging.getLogger(__name__)


def _script_port(script: str) -> int | None:
    match = re.search(r"(?:--port|-p)\s*=?\s*(\d{2,5})", script)
    if match:
        return int(match.group(1))
    match = re.search(r"\bPORT\s*=\s*(\d{2,5})\b", script, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _candidate_ports(root: pathlib.Path, dockerfile: pathlib.Path) -> list[int]:
    text = dockerfile.read_text(encoding="utf-8", errors="replace")
    plan = detect_project(root)
    ports = [int(value) for value in re.findall(r"^\s*EXPOSE\s+(\d+)", text, re.MULTILINE)]
    command_ports = [
        int(value)
        for value in re.findall(
            r"(?:--port[=\s]+|--port[\"']?\s*,\s*[\"']?|PORT[=\s])(\d{2,5})",
            text,
            re.IGNORECASE,
        )
    ]
    if ports:
        return list(dict.fromkeys(ports + command_ports))
    ports.extend(command_ports)
    if plan.language == "javascript":
        ports.extend((3000, 5173, 4173, 8080))
    else:
        ports.extend((8000, 8080, 5000))
    return list(dict.fromkeys(ports))


def _generated_dockerfile(root: pathlib.Path) -> str:
    plan = detect_project(root)
    if plan.language == "javascript":
        package = {}
        package_path = root / "package.json"
        if package_path.is_file():
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                package = {}
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        start_script = str(scripts.get("start", ""))
        if "start" in scripts and "vite" in start_script:
            port = _script_port(start_script) or 5173
            suffix = "" if _script_port(start_script) else f' --port {port}'
            command = f'CMD ["sh", "-c", "npm start -- --host 0.0.0.0{suffix}"]'
        elif "start" in scripts:
            port = _script_port(start_script) or 3000
            if "next" in start_script and "--hostname" not in start_script and " -H " not in f" {start_script} ":
                command = f'CMD ["sh", "-c", "npm start -- --hostname 0.0.0.0"]'
            else:
                command = 'CMD ["npm", "start"]'
        elif "dev" in scripts:
            dev_script = str(scripts["dev"])
            port = _script_port(dev_script) or 5173
            suffix = "" if _script_port(dev_script) else f' --port {port}'
            command = f'CMD ["sh", "-c", "npm run dev -- --host 0.0.0.0{suffix}"]'
        elif "preview" in scripts:
            preview_script = str(scripts["preview"])
            port = _script_port(preview_script) or 4173
            suffix = "" if _script_port(preview_script) else f' --port {port}'
            command = f'CMD ["sh", "-c", "npm run preview -- --host 0.0.0.0{suffix}"]'
        else:
            command = 'CMD ["npm", "run", "start"]'
            port = 3000
        return (
            "FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\n"
            "RUN npm ci || npm install\nCOPY . .\n"
            f"EXPOSE {port}\n{command}\n"
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
        candidate_ports = _candidate_ports(root, dockerfile)
        build = subprocess.run(
            ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
            capture_output=True, text=True, timeout=300,
        )
        result["build"] = {"passed": build.returncode == 0, "stdout": build.stdout[-4000:], "stderr": build.stderr[-4000:]}
        if build.returncode:
            result["error"] = "Docker image build failed"
            return result
        run_command = [
            "docker", "run", "-d", "--label", "phoenix.analysis=true",
        ]
        for candidate_port in candidate_ports:
            run_command.extend(["-p", f"127.0.0.1::{candidate_port}"])
        run_command.extend(["--name", container, image])
        run = subprocess.run(
            run_command,
            capture_output=True, text=True, timeout=30,
        )
        if run.returncode:
            result["error"] = run.stderr[-2000:]
            return result
        result["container_id"] = run.stdout.strip()
        published_ports = _published_ports(container)
        health = _probe_health(published_ports, 45)
        result["ports"] = published_ports
        result["health"] = health
        result["status"] = "ready" if health["healthy"] else "failed"
        result["container_status"] = _command(
            ["docker", "inspect", "-f", "{{.State.Status}}", container]
        )
        result["logs"] = _command(["docker", "logs", "--tail", "200", container])
        result["resources"] = _resources(container)
        return result
    except Exception as exc:
        result["logs"] = _command(["docker", "logs", "--tail", "200", container])
        result["container_status"] = _command(
            ["docker", "inspect", "-f", "{{.State.Status}}", container]
        )
        result["error"] = str(exc)
        return result
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True)
        subprocess.run(["docker", "rmi", "-f", image], capture_output=True, text=True)
        if generated and dockerfile:
            dockerfile.unlink(missing_ok=True)


def _published_ports(container: str) -> dict[int, int]:
    inspect = _command(["docker", "port", container])
    ports: dict[int, int] = {}
    for line in inspect.splitlines():
        match = re.match(r"(\d+)/\w+\s+->\s+[\d.]+:(\d+)", line.strip())
        if match:
            ports[int(match.group(1))] = int(match.group(2))
    if not ports:
        raise RuntimeError("Container did not publish any candidate port")
    return ports


def _probe_health(ports: dict[int, int], timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    paths = ("/health", "/api/health", "/")
    last_error = ""
    while time.monotonic() < deadline:
        for container_port, host_port in ports.items():
            for path in paths:
                try:
                    response = requests.get(f"http://127.0.0.1:{host_port}{path}", timeout=2)
                    if response.status_code < 500:
                        return {
                            "healthy": True,
                            "path": path,
                            "status_code": response.status_code,
                            "container_port": container_port,
                        }
                    last_error = f"{container_port}{path}: HTTP {response.status_code}"
                except requests.RequestException as exc:
                    last_error = f"{container_port}{path}: {exc}"
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
