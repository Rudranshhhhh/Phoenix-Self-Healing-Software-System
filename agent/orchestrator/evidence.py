"""Build LLM evidence from a runtime FailureReport.

Traceback paths are container paths (e.g. /app/app.py). They are mapped back to the
project folder on the host so the LLM sees the real source, marked with '# FILE:' lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

FRAME_RE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+?)\s*$')
MAX_FILE_CHARS = 20_000
MAX_FILES = 3


@dataclass
class Frame:
    file: str
    line: int
    function: str
    host_path: Optional[Path] = None  # set only for files inside the project
    rel_path: Optional[str] = None


def split_error(error: str) -> tuple[str, str]:
    """'KeyError: 'price'' -> ('KeyError', "'price'")."""
    text = (error or "").strip()
    last = text.splitlines()[-1].strip() if text else ""
    if ": " in last:
        error_type, message = last.split(": ", 1)
        error_type = error_type.strip() or "Error"
        return error_type, message.strip() or error_type
    return (last or "Error"), (last or "Unknown error")


def parse_frames(stack_trace: str) -> list[Frame]:
    frames = []
    for line in (stack_trace or "").splitlines():
        match = FRAME_RE.match(line)
        if match:
            frames.append(Frame(match["file"], int(match["line"]), match["func"]))
    return frames


def map_to_host(frames: list[Frame], project_dir: Path, container_workdir: str = "/app") -> list[Frame]:
    root = project_dir.resolve()
    prefix = container_workdir.rstrip("/") + "/"
    for frame in frames:
        path = frame.file.replace("\\", "/")
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        host = (root / rel).resolve()
        if root in host.parents and host.is_file():
            frame.host_path = host
            frame.rel_path = host.relative_to(root).as_posix()
    return frames


def build_relevant_code(frames: list[Frame]) -> str:
    picked: list[Frame] = []
    for frame in reversed(frames):
        if frame.host_path and frame.rel_path not in {p.rel_path for p in picked}:
            picked.append(frame)
        if len(picked) == MAX_FILES:
            break
    blocks = []
    for frame in picked:
        text = frame.host_path.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
        blocks.append(f"# FILE: {frame.rel_path}\n{text.rstrip()}\n")
    return "\n".join(blocks)


def build_evidence(report: Any, project_dir: Path, container_workdir: str = "/app") -> dict:
    """Returns a dict accepted by LLMEngine.run (EvidenceInput fields)."""
    error_type, message = split_error(report.error)
    frames = map_to_host(parse_frames(report.stack_trace), project_dir, container_workdir)
    project_frames = [f for f in frames if f.host_path]
    blame = project_frames[-1] if project_frames else None
    return {
        "error_type": error_type,
        "error_message": message,
        "file": blame.rel_path if blame else "unknown",
        "line": blame.line if blame else 0,
        "function_name": blame.function if blame else None,
        "relevant_code": build_relevant_code(frames) or None,
        "stack_trace": report.stack_trace or None,
        "extra_context": {
            "container_name": report.container_name,
            "exit_code": report.exit_code,
            "project": project_dir.name,
        },
    }
