"""
Phoenix Agent - Failure Store

Saves a FailureReport as a JSON file so the next stage (LLM engine or
orchestrator) can pick it up later, even from a different process.
Files are written atomically, so a reader never sees a half-written file.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agent.runtime.docker_runtime import FailureReport

DEFAULT_DIR = Path(".phoenix") / "failures"


def save_failure(report: FailureReport, out_dir: Path = DEFAULT_DIR) -> Path:
    """
    Write the report to <out_dir>/<timestamp>_<container>.json and return the path.

    File layout:
        saved_at : UTC timestamp
        event    : the team contract {error, stack_trace, container_id}
        details  : the full report (exit code, status, log tail, ...)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", report.container_name) or "container"
    base = f"{now.strftime('%Y%m%dT%H%M%S%f')}Z_{safe_name}"
    path = out_dir / f"{base}.json"
    counter = 1
    while path.exists():
        path = out_dir / f"{base}_{counter}.json"
        counter += 1

    payload = {
        "saved_at": now.isoformat(),
        "event": {
            "error": report.error,
            "stack_trace": report.stack_trace,
            "container_id": report.container_id,
        },
        "details": report.to_dict(),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def list_failures(out_dir: Path = DEFAULT_DIR) -> list[Path]:
    """Saved failure files, oldest first. Empty list if the folder does not exist."""
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return []
    return sorted(out_dir.glob("*.json"))


def load_failure(path: Path) -> dict:
    """Read a saved failure file back into a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))