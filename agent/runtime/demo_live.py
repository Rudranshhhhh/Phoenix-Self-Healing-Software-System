"""
Day-2 demo: a web app that STAYS RUNNING while a request fails.
Phoenix detects the traceback from the live log stream.

Run from the repo root:   python -m agent.runtime.demo_live
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from docker.errors import DockerException

from agent.runtime.docker_runtime import DockerRuntime
from agent.runtime.log_watcher import watch_for_failure

IMAGE_TAG = "phoenix-web-demo:latest"
CONTAINER_NAME = "phoenix-web-demo"
APP_DIR = Path(__file__).resolve().parents[2] / "demo" / "web_app"

_PROBE = (
    "import sys, urllib.request\n"
    "try:\n"
    "    urllib.request.urlopen('http://localhost:8080{path}', timeout=3)\n"
    "except Exception:\n"
    "    sys.exit(1)\n"
)


def _call(container, path: str) -> int:
    """Send an HTTP request to the app from INSIDE the container."""
    exit_code, _ = container.exec_run(["python", "-c", _PROBE.format(path=path)])
    return exit_code


def _trigger_failure(container) -> None:
    """Wait until the app is up, then call the broken endpoint."""
    for _ in range(20):
        if _call(container, "/health") == 0:
            break
        time.sleep(1)
    print("   (simulated user) GET /product  -> the app will log a traceback")
    _call(container, "/product")


def main() -> int:
    try:
        runtime = DockerRuntime()
        print("1. Building image...")
        runtime.build_image(APP_DIR, IMAGE_TAG)
        print("2. Starting container...")
        container = runtime.start(IMAGE_TAG, CONTAINER_NAME)
        threading.Timer(3.0, _trigger_failure, args=(container,)).start()
        print("3. Watching live logs (container keeps running)...")
        report = watch_for_failure(runtime, container, timeout=40, tail=0)
        runtime.remove(CONTAINER_NAME)
    except DockerException as exc:
        print(f"Docker problem: {exc}\nIs Docker Desktop running?")
        return 1

    if report is None:
        print("No failure detected within the timeout.")
        return 0
    print("4. FAILURE DETECTED while the container was still running:")
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())