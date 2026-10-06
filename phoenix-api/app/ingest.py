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

Environment = Literal["docker", "local"]


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
    start_line: Optional[int] = Field(default=None, ge=1)  # line in the real file where old_code starts


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
    environment: Optional[Environment] = None


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
    environment: Optional[Environment] = None  # for "validating", which has no validation yet
    branch: Optional[str] = None  # fix branch, sent with "validated"
    simulated: Optional[bool] = None  # set on "detected" by the demo replay (app/demo_run.py)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INC_RE = re.compile(r"^INC-\d+$")
_FRAME_RE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+?)\s*$')
_COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?)\b")
_HUNK_RE = re.compile(r"^@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@", re.MULTILINE)

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


def _lines(code: str) -> list[str]:
    return [l if l.endswith("\n") else l + "\n" for l in code.splitlines(keepends=True)]


def _shift_hunks(diff: str, offset: int) -> str:
    """Moves every @@ -a,b +c,d @@ header down by ``offset`` lines."""
    if not offset:
        return diff
    return _HUNK_RE.sub(
        lambda m: f"@@ -{int(m[1]) + offset}{m[2] or ''} +{int(m[3]) + offset}{m[4] or ''} @@", diff
    )


def infer_start_line(patch: InFilePatch, suspect_file: Optional[str], suspect_line: Optional[int]) -> Optional[int]:
    """Where old_code starts in the real file, guessed from the diagnosis.

    The diagnosis line is taken to be the first line the patch changes.
    """
    if not suspect_file or not suspect_line:
        return None
    a, b = _norm_path(patch.file), _norm_path(suspect_file)
    if not (a.endswith(b) or b.endswith(a)):
        return None
    matcher = difflib.SequenceMatcher(None, _lines(patch.old_code), _lines(patch.new_code), autojunk=False)
    first_change = next((i1 for tag, i1, _, _, _ in matcher.get_opcodes() if tag != "equal"), None)
    if first_change is None:
        return None
    start = suspect_line - first_change
    return start if start >= 1 else None


def build_diff(
    patches: list[InFilePatch], suspect_file: Optional[str] = None, suspect_line: Optional[int] = None
) -> str:
    """old_code/new_code pairs -> one unified diff the dashboard can parse.

    Hunk line numbers follow each patch's start_line; a lone patch without
    one gets it from the diagnosis (see infer_start_line).
    """
    chunks: list[str] = []
    for patch in patches:
        name = _norm_path(patch.file)
        start = patch.start_line
        if start is None and len(patches) == 1:
            start = infer_start_line(patch, suspect_file, suspect_line)
        diff = "".join(
            difflib.unified_diff(
                _lines(patch.old_code), _lines(patch.new_code), fromfile=f"a/{name}", tofile=f"b/{name}"
            )
        )
        chunks.append(_shift_hunks(diff, (start or 1) - 1))
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
            if ev.simulated is not None:
                cur["simulated"] = ev.simulated
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
                    "diff": build_diff(ev.patch.patches, diag.get("suspect_file"), diag.get("suspect_line")),
                    "files_changed": [_norm_path(p.file) for p in ev.patch.patches],
                }

            if ev.environment:
                cur["validation_environment"] = ev.environment  # kept until the validation arrives
            environment = (ev.validation and ev.validation.environment) or cur.get("validation_environment")

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
                    "environment": environment,
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
                    "environment": environment,
                }

            if ev.pull_request and ev.pull_request.pr_url:
                pr = ev.pull_request
                cur["pull_request"] = {
                    "number": pr.pr_number,
                    "url": pr.pr_url,
                    "branch": pr.head_branch,
                    "state": "open",
                }
                if pr.head_branch:
                    cur["fix_branch"] = pr.head_branch
            if ev.branch:
                cur["fix_branch"] = ev.branch

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

    def remove_simulated(self) -> list[str]:
        """Drops every simulated incident. Their id mappings stay (as "removed:<key>") so numbering keeps counting up."""
        with self._lock:
            gone = {k for k, v in self._incidents.items() if v.get("simulated")}
            if not gone:
                return []
            for incident_id in gone:
                del self._incidents[incident_id]
            self._ids = {
                (f"removed:{key}" if value in gone and not key.startswith("removed:") else key): value
                for key, value in self._ids.items()
            }
            self._save()
            return sorted(gone)

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
            "fix_branch": None,
            "simulated": False,
            "timeline": [],
            "created_at": at,
            "updated_at": at,
        }


_DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "incidents.json"
store = IncidentStore(Path(os.environ.get("PHOENIX_DATA_FILE", str(_DEFAULT_FILE))))
