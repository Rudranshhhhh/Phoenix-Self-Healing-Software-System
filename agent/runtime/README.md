# Phoenix Docker Runtime (`agent/runtime/`)

Runs a project in Docker, watches it for runtime errors, and hands the error to the next stage.

## What it does
1. Builds an image from a folder that contains a `Dockerfile`.
2. Starts a container named `phoenix-run-<folder>` (label `phoenix.managed=true`).
3. Watches the container: live log stream (a traceback is caught while the app keeps running)
   and crashes (non-zero exit code, OOMKilled).
4. Always removes the container afterwards.
5. Returns the failure in the agreed format, and can save it to disk.

## Output (Agent -> Incident Manager)
    {"error": "KeyError: 'price'", "stack_trace": "Traceback ...", "container_id": "..."}

## Use from Python
    from pathlib import Path
    from agent.runtime.project_monitor import monitor_project, to_agent_event
    from agent.runtime.failure_store import save_failure, list_failures, load_failure

    report = monitor_project(Path("path/to/project"), timeout=30)   # None = no failure seen
    if report:
        event = to_agent_event(report)        # the 3-key message
        path = save_failure(report)           # optional: saves .phoenix/failures/<time>_<name>.json
    # later, from another process:
    latest = load_failure(list_failures()[-1])["event"]

## Use from the command line (repo root, Docker Desktop running)
    python -m agent.runtime.project_monitor demo\broken_app
    python -m agent.runtime.project_monitor demo\broken_app --save-dir .phoenix\failures

## Files
- `docker_runtime.py`  build / run / remove / crash detection (`DockerRuntime`, `FailureReport`)
- `log_watcher.py`     live traceback detection in a running container
- `project_monitor.py` one call for a whole project + the command-line tool
- `failure_store.py`   save / list / load failure files
- `demo*.py`, `../../demo/` small broken apps used for demos

## Not included
Cloning GitHub repos, source-code/git-diff collection, publishing ports, environment variables.
Tests: `python -m pytest agent\tests -q` (no Docker needed).