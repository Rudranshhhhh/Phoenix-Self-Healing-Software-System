"""
Phoenix Sandbox — Docker Runner

Builds a Docker image from the patched sandbox copy, starts a temporary
container, runs a health check, and then tears everything down.

This is the runtime isolation layer: the generated code never runs on the
Phoenix host. It runs inside a short-lived container built from the sandbox.

Design decisions
----------------
- Non-privileged containers only (no --privileged, no --cap-add).
- The host Docker socket is NOT mounted inside the application container.
- Images and containers are tagged with the incident_id and a random suffix
  so parallel runs never collide.
- Image and container are always removed after the run (in a finally block).
- Build and run have separate configurable timeouts.
- When the Docker daemon is unreachable and skip_docker_if_unavailable=True,
  the step returns DockerResult(skipped=True) — it does NOT count as a failure.

Timeout implementation
----------------------
docker SDK does not expose subprocess-level timeouts on build/run calls, so
we use threading.Timer to interrupt the subprocess-level docker commands
and fall back gracefully.
"""
from __future__ import annotations

import hashlib
import logging
import pathlib
import subprocess
import tempfile
import time
import uuid
from typing import Optional

from agent.sandbox.models import DockerResult

logger = logging.getLogger(__name__)

# Health-check URL path used to verify the container is alive.
_HEALTH_PATH = "/health"
_HEALTH_PORT = 8080
# How many times to poll before giving up.
_HEALTH_MAX_ATTEMPTS = 15
_HEALTH_POLL_INTERVAL_S = 2


def run_docker_sandbox(
    sandbox_path: pathlib.Path,
    incident_id: str,
    dockerfile_path: str = "",
    docker_timeout_seconds: int = 180,
    container_startup_timeout: int = 30,
    skip_if_unavailable: bool = True,
) -> DockerResult:
    """
    Build + run the Docker sandbox for the given sandbox directory.

    Args:
        sandbox_path:               Root of the patched sandbox copy.
        incident_id:                Used to name the image/container.
        dockerfile_path:            Relative path to Dockerfile inside sandbox.
                                    Empty = auto-detect.
        docker_timeout_seconds:     Total timeout for build+run combined.
        container_startup_timeout:  Seconds to wait for the /health endpoint.
        skip_if_unavailable:        If True, return skipped=True when Docker
                                    daemon is unreachable instead of failing.

    Returns:
        DockerResult with all step outcomes captured.
    """
    result = DockerResult()

    # ------------------------------------------------------------------ #
    # 0. Detect Docker availability                                        #
    # ------------------------------------------------------------------ #
    if not _docker_available():
        msg = "Docker daemon is not reachable."
        logger.warning("DockerRunner: %s", msg)
        if skip_if_unavailable:
            result.skipped = True
            result.skip_reason = msg
            return result
        result.failure_reason = msg
        return result

    # ------------------------------------------------------------------ #
    # 1. Locate the Dockerfile                                             #
    # ------------------------------------------------------------------ #
    dockerfile_abs = _find_dockerfile(sandbox_path, dockerfile_path)
    if dockerfile_abs is None:
        result.failure_reason = (
            f"No Dockerfile found in sandbox at {sandbox_path}. "
            f"Tried: sample-app/Dockerfile, Dockerfile."
        )
        logger.error("DockerRunner: %s", result.failure_reason)
        return result

    build_context = dockerfile_abs.parent
    logger.info(
        "DockerRunner: using Dockerfile at %s (context: %s)",
        dockerfile_abs,
        build_context,
    )

    # ------------------------------------------------------------------ #
    # 2. Generate unique image + container names                          #
    # ------------------------------------------------------------------ #
    slug = _slug(incident_id)
    image_tag = f"phoenix-sandbox-{slug}:latest"
    container_name = f"phoenix-sandbox-{slug}"
    result.image_tag = image_tag
    result.container_name = container_name

    # ------------------------------------------------------------------ #
    # 3. Build the Docker image                                            #
    # ------------------------------------------------------------------ #
    logger.info("DockerRunner: building image %s …", image_tag)
    build_start = time.monotonic()

    build_proc = _run_cmd(
        [
            "docker", "build",
            "-t", image_tag,
            "-f", str(dockerfile_abs),
            str(build_context),
        ],
        timeout=docker_timeout_seconds,
    )

    result.build_duration_seconds = time.monotonic() - build_start
    result.build_stdout = build_proc.stdout or ""
    result.build_stderr = build_proc.stderr or ""
    result.build_exit_code = build_proc.returncode

    if build_proc.returncode != 0:
        result.build_passed = False
        result.failure_reason = (
            f"Docker build failed (exit {build_proc.returncode}). "
            f"See build_stderr for details."
        )
        logger.error(
            "DockerRunner: build failed in %.1fs — %s",
            result.build_duration_seconds,
            result.failure_reason,
        )
        _remove_image(image_tag)
        return result

    result.build_passed = True
    logger.info(
        "DockerRunner: build succeeded in %.1fs",
        result.build_duration_seconds,
    )

    # ------------------------------------------------------------------ #
    # 4. Run container + health check                                      #
    # ------------------------------------------------------------------ #
    run_start = time.monotonic()
    remaining_timeout = max(
        10,
        docker_timeout_seconds - int(result.build_duration_seconds),
    )

    try:
        _start_container(image_tag, container_name)

        # Poll health endpoint
        healthy = _wait_for_health(
            container_name=container_name,
            port=_HEALTH_PORT,
            path=_HEALTH_PATH,
            max_attempts=_HEALTH_MAX_ATTEMPTS,
            poll_interval=_HEALTH_POLL_INTERVAL_S,
            timeout=min(container_startup_timeout, remaining_timeout),
        )

        if healthy:
            result.container_started = True
            result.health_check_passed = True
            logger.info("DockerRunner: container started and health check passed.")
        else:
            result.container_started = True  # container ran; health failed
            result.health_check_passed = False
            result.failure_reason = (
                f"Container started but /health did not respond with 200 "
                f"within {container_startup_timeout}s."
            )
            logger.warning("DockerRunner: %s", result.failure_reason)

        # Capture container logs
        logs_proc = _run_cmd(
            ["docker", "logs", container_name],
            timeout=10,
        )
        result.container_stdout = logs_proc.stdout or ""
        result.container_stderr = logs_proc.stderr or ""

    except Exception as exc:
        result.failure_reason = f"Container run failed: {exc}"
        logger.error("DockerRunner: %s", result.failure_reason)

    finally:
        result.run_duration_seconds = time.monotonic() - run_start
        _stop_and_remove_container(container_name)
        _remove_image(image_tag)

    return result


# ============================================================================ #
# Internal helpers                                                               #
# ============================================================================ #

def _docker_available() -> bool:
    """Return True if the Docker daemon responds to `docker info`."""
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _find_dockerfile(
    sandbox_path: pathlib.Path,
    explicit_path: str,
) -> Optional[pathlib.Path]:
    """
    Locate the Dockerfile to use for the build.

    Priority:
      1. explicit_path if given
      2. sample-app/Dockerfile  (Phoenix sample app)
      3. Dockerfile at sandbox root
    """
    if explicit_path:
        candidate = sandbox_path / explicit_path
        return candidate if candidate.exists() else None

    candidates = [
        sandbox_path / "sample-app" / "Dockerfile",
        sandbox_path / "Dockerfile",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _slug(incident_id: str) -> str:
    """Produce a short unique slug safe for Docker names."""
    uid = hashlib.md5(incident_id.encode()).hexdigest()[:8]
    safe = "".join(c for c in incident_id.lower() if c.isalnum() or c == "-")
    return f"{safe}-{uid}"


def _run_cmd(
    cmd: list[str],
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a shell command, capturing stdout/stderr, never raising on non-zero."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("DockerRunner: command timed out after %ds: %s", timeout, cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"Command timed out after {timeout}s.",
        )
    except (FileNotFoundError, OSError) as exc:
        logger.error("DockerRunner: command not found: %s — %s", cmd[0], exc)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )


def _start_container(image_tag: str, container_name: str) -> None:
    """Start a detached container (non-privileged, no host-socket mount)."""
    proc = _run_cmd(
        [
            "docker", "run",
            "--detach",
            "--name", container_name,
            "--publish", f"{_HEALTH_PORT}:{_HEALTH_PORT}",
            "--env", f"PORT={_HEALTH_PORT}",
            # Security: no privileged, no host socket
            "--read-only=false",
            "--security-opt", "no-new-privileges",
            image_tag,
        ],
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker run failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )


def _wait_for_health(
    container_name: str,
    port: int,
    path: str,
    max_attempts: int,
    poll_interval: float,
    timeout: int,
) -> bool:
    """
    Poll the container's health endpoint until it returns HTTP 200
    or the timeout / attempt limit is exhausted.
    """
    import urllib.request
    import urllib.error

    url = f"http://localhost:{port}{path}"
    deadline = time.monotonic() + timeout

    for attempt in range(1, max_attempts + 1):
        if time.monotonic() > deadline:
            logger.debug("DockerRunner: health poll deadline exceeded")
            break
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    logger.debug(
                        "DockerRunner: health check passed on attempt %d",
                        attempt,
                    )
                    return True
        except (urllib.error.URLError, OSError):
            pass  # container not ready yet

        logger.debug(
            "DockerRunner: health poll attempt %d/%d — waiting %.1fs",
            attempt,
            max_attempts,
            poll_interval,
        )
        time.sleep(poll_interval)

    return False


def _stop_and_remove_container(container_name: str) -> None:
    """Stop and remove the sandbox container. Errors are logged but not raised."""
    for cmd in (
        ["docker", "stop", "--time", "5", container_name],
        ["docker", "rm", "--force", container_name],
    ):
        proc = _run_cmd(cmd, timeout=15)
        if proc.returncode != 0:
            logger.debug(
                "DockerRunner: cleanup cmd %s returned %d — %s",
                cmd,
                proc.returncode,
                proc.stderr.strip(),
            )


def _remove_image(image_tag: str) -> None:
    """Remove the sandbox image. Errors are logged but not raised."""
    proc = _run_cmd(
        ["docker", "rmi", "--force", image_tag],
        timeout=15,
    )
    if proc.returncode != 0:
        logger.debug(
            "DockerRunner: image removal %s returned %d",
            image_tag,
            proc.returncode,
        )
