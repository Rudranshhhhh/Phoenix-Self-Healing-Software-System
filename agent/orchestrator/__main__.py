"""python -m agent.orchestrator <project_dir> [--timeout 60] [--no-lint] [--workdir /app] [--api-url URL]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .ingest_client import IngestClient
from .orchestrator import REPO_ROOT, Orchestrator

EXIT_CODES = {"no_failure": 0, "validated": 0, "pr_opened": 0, "rejected": 2}


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent.orchestrator",
        description="Run a project in Docker; if it crashes, diagnose, patch and validate the fix. "
        "Progress is sent to phoenix-api.",
    )
    parser.add_argument("project_dir")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for a crash")
    parser.add_argument("--no-lint", action="store_true", help="skip flake8 in the sandbox")
    parser.add_argument("--workdir", default="/app", help="WORKDIR inside the container")
    parser.add_argument("--api-url", default=None, help="phoenix-api URL (default PHOENIX_API_URL or :8000)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _load_env()
    project = Path(args.project_dir)
    if not project.is_dir():
        parser.error(f"not a folder: {project}")

    orchestrator = Orchestrator(
        ingest=IngestClient(base_url=args.api_url),
        container_workdir=args.workdir,
        run_lint=not args.no_lint,
        timeout=args.timeout,
    )
    result = orchestrator.run(project)
    print(f"\nResult: {result.status}   dashboard id: {result.dashboard_id or '-'}")
    if result.workspace:
        print(f"Workspace: {result.workspace}")
    if result.message:
        print(result.message)
    return EXIT_CODES.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
