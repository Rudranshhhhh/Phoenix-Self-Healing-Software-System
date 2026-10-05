"""
Phoenix Agent - Project Monitor (Day 3)

Point Phoenix at ANY folder that contains a Dockerfile: it builds the image,
runs the container, watches it (live logs + crash), always cleans up, and
returns the failure in the team format {error, stack_trace, container_id}.

CLI (from the repo root):
    python -m agent.runtime.project_monitor <project_folder> [--timeout 30] [--full]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

from docker.errors import APIError, BuildError, DockerException

from agent.runtime.docker_runtime import DockerRuntime, FailureReport
from agent.runtime.log_watcher import watch_for_failure

# "phoenix-run-" prefix keeps us away from the compose containers
# (phoenix-backend, phoenix-agent, ...) that start() would otherwise replace.
_NAME_PREFIX = "phoenix-run-"


class ProjectError(Exception):
    """A problem with the project itself (bad path, no Dockerfile, build failed)."""


def to_agent_event(report: FailureReport) -> dict:
    """The agreed Agent -> Incident Manager message, and nothing else."""
    return {
        "error": report.error,
        "stack_trace": report.stack_trace,
        "container_id": report.container_id,
    }


def _slug(folder_name: str) -> str:
    slug = re.sub(r"[^a-z0-9_.-]+", "-", folder_name.lower()).strip("-.")
    return slug or "app"


def monitor_project(
    project_dir: Path,
    runtime: Optional[DockerRuntime] = None,
    timeout: float = 60.0,
) -> Optional[FailureReport]:
    """
    Build, run and watch the project. Returns a FailureReport, or None if no
    failure appeared within `timeout`. The container is always removed.
    Raises ProjectError for project problems (never leaves a container behind).
    """
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        raise ProjectError(f"Project folder not found: {project_dir}")
    if not (project_dir / "Dockerfile").is_file():
        raise ProjectError(f"No Dockerfile found in: {project_dir}")

    runtime = runtime or DockerRuntime()
    slug = _slug(project_dir.resolve().name)
    image_tag = f"phoenix-run-{slug}:latest"
    container_name = f"{_NAME_PREFIX}{slug}"

    try:
        runtime.build_image(project_dir, image_tag)
    except (BuildError, APIError) as exc:
        raise ProjectError(f"Docker build failed: {exc}") from exc

    container = runtime.start(image_tag, container_name)
    try:
        return watch_for_failure(runtime, container, timeout=timeout, tail="all")
    finally:
        runtime.remove(container_name)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a project in Docker and report its first failure.")
    parser.add_argument("project", type=Path, help="folder containing a Dockerfile")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds to watch (default 30)")
    parser.add_argument("--full", action="store_true", help="print the full report, not just the team format")
    args = parser.parse_args(argv)

    try:
        report = monitor_project(args.project, timeout=args.timeout)
    except ProjectError as exc:
        print(f"Phoenix: {exc}")
        return 2
    except DockerException as exc:
        print(f"Docker problem: {exc}\nIs Docker Desktop running?")
        return 1

    if report is None:
        print("No failure detected within the timeout.")
        return 0
    payload = report.to_dict() if args.full else to_agent_event(report)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())