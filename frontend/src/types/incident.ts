// ---------------------------------------------------------------------------
// Phoenix incident model. Mirrors the FastAPI JSON exactly (snake_case,
// ISO-8601 UTC timestamps). Sections are null until that stage is reached.
// ---------------------------------------------------------------------------

export const INCIDENT_STATUSES = [
  "detected",
  "diagnosing",
  "fix_proposed",
  "validating",
  "validated",
  "rejected",
  "pr_opened",
] as const;

export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];

export type SourceType = "github_actions" | "docker_runtime";

export interface IncidentSource {
  type: SourceType;
  workflow_run_url: string | null; // github_actions only
  container: string | null;        // docker_runtime only
  commit_sha: string | null;
}

export interface StackFrame {
  file: string;
  line: number;
  function: string;
  code: string;
  blame: boolean; // the frame the diagnosis points at
}

export interface IncidentError {
  exception_type: string;
  message: string;
  stack_trace: string; // raw traceback text
  frames: StackFrame[];
}

export interface Diagnosis {
  root_cause: string;
  explanation: string;
  suspect_file: string | null;
  suspect_line: number | null;
  confidence: number | null; // 0..1
  context_files: string[];
}

export interface Patch {
  summary: string;
  diff: string; // raw unified diff
  files_changed: string[];
}

export interface Validation {
  result: "PASS" | "FAIL";
  tests_run: number;
  tests_passed: number;
  bug_reproduced_before_patch: boolean;
  bug_reproduces_after_patch: boolean;
  duration_seconds: number;
  output: string; // test runner output
  rejection_reason: string | null; // set when result is FAIL
  finished_at: string;
}

export interface PullRequest {
  number: number;
  url: string;
  branch: string; // e.g. phoenix/fix/INC-001
  state: "open" | "merged" | "closed";
}

export interface TimelineEntry {
  status: IncidentStatus;
  at: string;
  message: string | null;
}

export interface Incident {
  id: string; // e.g. INC-001
  repo: string; // owner/name
  status: IncidentStatus;
  source: IncidentSource;
  error: IncidentError;
  diagnosis: Diagnosis | null;
  patch: Patch | null;
  validation: Validation | null;
  pull_request: PullRequest | null;
  timeline: TimelineEntry[];
  created_at: string;
  updated_at: string;
}

/** One row in GET /api/incidents. */
export interface IncidentSummary {
  id: string;
  repo: string;
  status: IncidentStatus;
  exception_type: string;
  message: string;
  source_type: SourceType;
  validation_result: "PASS" | "FAIL" | null;
  pr_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentListResponse {
  items: IncidentSummary[];
  total: number;
  page: number;
  page_size: number;
}
