"""Ingest: turns agent pipeline events into dashboard incidents.

The agent POSTs one event per stage to /api/ingest/events. Field names in the
payload follow the agent's own models (DiagnosisResult, PatchResult,
ValidationResult, PRResult); this module maps them to the dashboard Incident.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .models import Incident

EventName = Literal[
    "detected",
    "diagnosing",
    "fix_proposed",
    "validating",
    "validated",
    "rejected",
    "failed",
    "pr_opened",
]


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


class InSource(BaseModel):
    type: Literal["github_actions", "docker_runtime"] = "docker_runtime"
    workflow_run_url: Optional[str] = None
    container: Optional[str] = None
    commit_sha: Optional[str] = None


class InError(BaseModel):
    exception_type: str = ""
    message: str = ""
    stack_trace: str = ""


class InDiagnosis(BaseModel):
    root_cause: str = ""
    explanation: str = ""
    affected_file: Optional[str] = None
    affected_line: Optional[int] = None
    confidence: Optional[float] = None


class InFilePatch(BaseModel):
    file: str
    old_code: str = ""
    new_code: str = ""


class InPatch(BaseModel):
    explanation: str = ""
    patches: list[InFilePatch] = Field(default_factory=list)


class InValidation(BaseModel):
    validated: bool
    reason: str = ""
    test_stdout: str = ""
    test_stderr: str = ""
    duration_seconds: float = 0.0
    completed_at: Optional[datetime] = None
    original_failure_resolved: Optional[bool] = None


class InPullRequest(BaseModel):
    pr_number: Optional[int] = None
    pr_url: str = ""
    head_branch: str = ""


class IngestEvent(BaseModel):
    incident_id: str = Field(min_length=1, max_length=100)
    event: EventName
    at: Optional[datetime] = None
    message: Optional[str] = None
    repo: Optional[str] = None
    source: Optional[InSource] = None
    error: Optional[InError] = None
    diagnosis: Optional[InDiagnosis] = None
    patch: Optional[InPatch] = None
    validation: Optional[InValidation] = None
    pull_request: Optional[InPullRequest] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INC_RE = re.compile(r"^INC-\d+$")
_FRAME_RE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+?)\s*$')
_COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?)\b")

DEFAULT_MESSAGES = {
    "detected": "Failure detected",
    "diagnosing": "Diagnosing the failure",
    "fix_proposed": "Patch generated",
    "validating": "Testing the patch in a sandbox",
    "validated": "Sandbox: tests pass and the original error no longer reproduces",
    "rejected": "Patch rejected",
    "pr_opened": "Pull request opened",
}


def _iso(value: Optional[datetime] = None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_path(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def parse_frames(stack_trace: str, suspect_file: Optional[str], suspect_line: Optional[int]) -> list[dict]:
    """Python traceback text -> frames; the frame matching the diagnosis gets blame."""
    lines = stack_trace.splitlines()
    frames: list[dict] = []
    for i, line in enumerate(lines):
        match = _FRAME_RE.match(line)
        if not match:
            continue
        code = ""
        if i + 1 < len(lines) and lines[i + 1].startswith("    ") and not _FRAME_RE.match(lines[i + 1]):
            code = lines[i + 1].strip()
        frames.append(
            {
                "file": match["file"],
                "line": int(match["line"]),
                "function": match["func"],
                "code": code,
                "blame": False,
            }
        )
    if not frames:
        return frames

    blame = None
    if suspect_file:
        target = _norm_path(suspect_file)
        same_file = [f for f in frames if _norm_path(f["file"]).endswith(target)]
        exact = [f for f in same_file if suspect_line and f["line"] == suspect_line]
        if exact:
            blame = exact[-1]
        elif same_file:
            blame = same_file[-1]
    (blame or frames[-1])["blame"] = True
    return frames


def build_diff(patches: list[InFilePatch]) -> str:
    """old_code/new_code pairs -> one unified diff the dashboard can parse."""
    chunks: list[str] = []
    for patch in patches:
        name = _norm_path(patch.file)
        old = [l if l.endswith("\n") else l + "\n" for l in patch.old_code.splitlines(keepends=True)]
        new = [l if l.endswith("\n") else l + "\n" for l in patch.new_code.splitlines(keepends=True)]
        chunks.extend(difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}"))
    return "".join(chunks)


def count_tests(output: str) -> tuple[Optional[int], Optional[int]]:
    """Reads pytest's summary ('3 failed, 61 passed') -> (tests_run, tests_passed)."""
    counts: dict[str, int] = {}
    for number, kind in _COUNT_RE.findall(output):
        counts["error" if kind.startswith("error") else kind] = int(number)
    if not counts:
        return None, None
    passed = counts.get("passed", 0)
    return passed + counts.get("failed", 0) + counts.get("error", 0), passed


def demo_fixtures_enabled() -> bool:
    return os.environ.get("DEMO_FIXTURES", "1").strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class IncidentStore:
    """Dashboard incidents kept in one JSON file. Thread-safe, atomic writes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._incidents: dict[str, dict] = {}
        self._ids: dict[str, str] = {}  # agent incident id -> dashboard id
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._incidents = raw.get("incidents", {})
        self._ids = raw.get("ids", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ids": self._ids, "incidents": self._incidents}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _dashboard_id(self, external_id: str) -> str:
        if external_id in self._ids:
            return self._ids[external_id]
        if _INC_RE.match(external_id):
            new_id = external_id
        else:
            used = [int(v.split("-")[1]) for v in self._ids.values() if _INC_RE.match(v)]
            new_id = f"INC-{max([100, *used]) + 1:03d}"
        self._ids[external_id] = new_id
        return new_id

    def list(self) -> list[Incident]:
        with self._lock:
            return [Incident.model_validate(v) for v in self._incidents.values()]

    def get(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            data = self._incidents.get(incident_id)
            return Incident.model_validate(data) if data else None

    def apply(self, ev: IngestEvent) -> Incident:
        with self._lock:
            incident_id = self._dashboard_id(ev.incident_id)
            at = _iso(ev.at)
            cur = json.loads(json.dumps(self._incidents.get(incident_id) or self._new(incident_id, ev, at)))

            if ev.repo:
                cur["repo"] = ev.repo
            if ev.source:
                cur["source"] = ev.source.model_dump()
            if ev.error:
                cur["error"].update(
                    exception_type=ev.error.exception_type or cur["error"]["exception_type"],
                    message=ev.error.message or cur["error"]["message"],
                    stack_trace=ev.error.stack_trace or cur["error"]["stack_trace"],
                )
            if ev.diagnosis:
                d = ev.diagnosis
                cur["diagnosis"] = {
                    "root_cause": d.root_cause,
                    "explanation": d.explanation,
                    "suspect_file": d.affected_file or None,
                    "suspect_line": d.affected_line or None,
                    "confidence": d.confidence,
                    "context_files": [],
                }
            diag = cur.get("diagnosis") or {}
            cur["error"]["frames"] = parse_frames(
                cur["error"]["stack_trace"], diag.get("suspect_file"), diag.get("suspect_line")
            )

            if ev.patch:
                cur["patch"] = {
                    "summary": ev.patch.explanation or DEFAULT_MESSAGES["fix_proposed"],
                    "diff": build_diff(ev.patch.patches),
                    "files_changed": [_norm_path(p.file) for p in ev.patch.patches],
                }

            if ev.validation:
                v = ev.validation
                output = v.test_stdout + (("\n" + v.test_stderr) if v.test_stderr else "")
                tests_run, tests_passed = count_tests(output)
                resolved = v.original_failure_resolved if v.original_failure_resolved is not None else v.validated
                cur["validation"] = {
                    "result": "PASS" if v.validated else "FAIL",
                    "tests_run": tests_run,
                    "tests_passed": tests_passed,
                    "bug_reproduced_before_patch": None,
                    "bug_reproduces_after_patch": not resolved,
                    "duration_seconds": v.duration_seconds,
                    "output": output,
                    "rejection_reason": None if v.validated else (v.reason or ev.message or "Validation failed"),
                    "finished_at": _iso(v.completed_at or ev.at),
                }
            elif ev.event == "failed" and not cur.get("validation"):
                cur["validation"] = {
                    "result": "FAIL",
                    "tests_run": None,
                    "tests_passed": None,
                    "bug_reproduced_before_patch": None,
                    "bug_reproduces_after_patch": True,
                    "duration_seconds": 0.0,
                    "output": "",
                    "rejection_reason": ev.message or "The pipeline stopped with an error",
                    "finished_at": at,
                }

            if ev.pull_request and ev.pull_request.pr_url:
                pr = ev.pull_request
                cur["pull_request"] = {
                    "number": pr.pr_number,
                    "url": pr.pr_url,
                    "branch": pr.head_branch,
                    "state": "open",
                }

            status = "rejected" if ev.event == "failed" else ev.event
            cur["status"] = status
            entry = {"status": status, "at": at, "message": ev.message or DEFAULT_MESSAGES[status]}
            if cur["timeline"] and cur["timeline"][-1]["status"] == status:
                cur["timeline"][-1] = entry
            else:
                cur["timeline"].append(entry)
            cur["updated_at"] = at

            incident = Incident.model_validate(cur)  # raises before anything is saved
            self._incidents[incident_id] = cur
            self._save()
            return incident

    @staticmethod
    def _new(incident_id: str, ev: IngestEvent, at: str) -> dict:
        return {
            "id": incident_id,
            "repo": ev.repo or os.environ.get("PHOENIX_REPO", "phoenix-demo/orders-api"),
            "status": "detected",
            "source": {"type": "docker_runtime", "workflow_run_url": None, "container": None, "commit_sha": None},
            "error": {"exception_type": "UnknownError", "message": "", "stack_trace": "", "frames": []},
            "diagnosis": None,
            "patch": None,
            "validation": None,
            "pull_request": None,
            "timeline": [],
            "created_at": at,
            "updated_at": at,
        }


_DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "incidents.json"
store = IncidentStore(Path(os.environ.get("PHOENIX_DATA_FILE", str(_DEFAULT_FILE))))
