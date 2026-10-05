"""
Day-1 demo: build the broken app, run it in Docker, detect the crash.

Run from the repo root:   python -m agent.runtime.demo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from docker.errors import DockerException

from agent.runtime.docker_runtime import DockerRuntime

IMAGE_TAG = "phoenix-demo-app:latest"
CONTAINER_NAME = "phoenix-demo-app"
APP_DIR = Path(__file__).resolve().parents[2] / "demo" / "broken_app"


def main() -> int:
    try:
        runtime = DockerRuntime()
        print("1. Building image...")
        runtime.build_image(APP_DIR, IMAGE_TAG)
        print("2. Starting container...")
        container = runtime.start(IMAGE_TAG, CONTAINER_NAME)
        print("3. Watching container...")
        if not runtime.wait_for_exit(container, timeout=60):
            print("Container is still running - no failure detected.")
            runtime.remove(CONTAINER_NAME)
            return 0
        report = runtime.collect_failure(container)
        runtime.remove(CONTAINER_NAME)
    except DockerException as exc:
        print(f"Docker problem: {exc}\nIs Docker Desktop running?")
        return 1

    if report is None:
        print("Container exited cleanly (exit code 0). Nothing to report.")
        return 0
    print("4. FAILURE DETECTED:")
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())