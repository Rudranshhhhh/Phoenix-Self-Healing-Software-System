import type {
  Incident,
  IncidentListResponse,
  IncidentStatus,
  IncidentSummary,
} from "../types/incident";
import type { GithubUser } from "../types/phoenix";

// ---------------------------------------------------------------------------
// Phoenix API client. In dev BASE is empty, so requests go to /api on the
// Vite server and its proxy forwards them to phoenix-api on port 8000.
// ---------------------------------------------------------------------------

const BASE: string = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    signal,
    credentials: "include",          // send the session cookie on every request
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`GET ${path} failed with ${response.status} ${response.statusText}`.trim());
  }
  return (await response.json()) as T;
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`DELETE ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

async function writeJson<T>(path: string, method: "PUT", body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${method} ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Existing incident endpoints (unchanged)
// ---------------------------------------------------------------------------

export function getIncidents(repository?: string, signal?: AbortSignal): Promise<IncidentListResponse> {
  const query = repository ? `?page_size=100&repository=${encodeURIComponent(repository)}` : "?page_size=100";
  return getJson<IncidentWireList>(`/api/incidents${query}`, signal).then((response) => ({
    items: response.items ?? response.incidents.map(toSummary),
    total: response.total,
    page: response.page,
    page_size: response.page_size,
  }));
}

export function getIncident(id: string, signal?: AbortSignal): Promise<Incident> {
  return getJson<Incident | IncidentWire>(`/api/incidents/${encodeURIComponent(id)}`, signal).then(
    (incident) => ("incident_id" in incident ? toIncident(incident) : incident),
  );
}

type IncidentWire = {
  incident_id: string;
  source: "github_ci" | "docker_runtime";
  repository: string;
  status: string;
  payload?: Record<string, unknown>;
  evidence?: Record<string, unknown> | null;
  diagnosis?: Record<string, unknown> | null;
  patch?: Record<string, unknown> | null;
  validation_result?: Record<string, unknown> | null;
  git_branch?: string | null;
  pr_url?: string | null;
  pr_number?: number | null;
  created_at: string;
  updated_at: string;
  timeline?: Array<{ status: string; timestamp: string; message?: string }>;
  error_reason?: string | null;
};

type IncidentWireList = {
  incidents: IncidentWire[];
  items?: IncidentSummary[];
  total: number;
  page: number;
  page_size: number;
};

function statusForUi(status: string): IncidentStatus {
  if (status === "queued_for_agent" || status === "agent_processing") {
    return "diagnosing";
  }
  if (status === "agent_failed") {
    return "rejected";
  }
  if (
    status === "detected" ||
    status === "diagnosing" ||
    status === "fix_proposed" ||
    status === "validating" ||
    status === "validated" ||
    status === "rejected" ||
    status === "pr_opened"
  ) {
    return status;
  }
  return "rejected";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function toSummary(incident: IncidentWire): IncidentSummary {
  const payload = incident.payload ?? {};
  const evidence = incident.evidence ?? {};
  const validation = incident.validation_result;
  return {
    id: incident.incident_id,
    repo: incident.repository,
    status: statusForUi(incident.status),
    exception_type: stringValue(payload.error_type) || stringValue(evidence.error_type) || "Failure",
    message: stringValue(payload.error_message) || incident.error_reason || "Incident detected",
    source_type: incident.source === "github_ci" ? "github_actions" : "docker_runtime",
    validation_result:
      validation?.validated === true ? "PASS" : validation?.validated === false ? "FAIL" : null,
    pr_url: incident.pr_url ?? null,
    created_at: incident.created_at,
    updated_at: incident.updated_at,
  };
}

function toIncident(incident: IncidentWire): Incident {
  const payload = incident.payload ?? {};
  const evidence = incident.evidence ?? {};
  const diagnosis = incident.diagnosis;
  const patch = incident.patch;
  const validation = incident.validation_result;
  const summary = toSummary(incident);
  const stackTrace = stringValue(payload.stack_trace) || stringValue(evidence.stack_trace);

  return {
    ...summary,
    source: {
      type: summary.source_type,
      workflow_run_url: stringValue(payload.run_url) || null,
      container: stringValue(payload.container_name) || null,
      commit_sha: stringValue(payload.commit) || null,
    },
    error: {
      exception_type: summary.exception_type,
      message: summary.message,
      stack_trace: stackTrace,
      frames: [],
    },
    diagnosis: diagnosis
      ? {
          root_cause: stringValue(diagnosis.root_cause),
          explanation: stringValue(diagnosis.explanation),
          suspect_file: stringValue(diagnosis.affected_file) || null,
          suspect_line: typeof diagnosis.affected_line === "number" ? diagnosis.affected_line : null,
          confidence: typeof diagnosis.confidence === "number" ? diagnosis.confidence : null,
          context_files: [],
        }
      : null,
    patch: patch
      ? {
          summary: stringValue(patch.explanation),
          diff: stringValue(patch.diff),
          files_changed: Array.isArray(patch.patches)
            ? patch.patches
                .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
                .map((item) => stringValue(item.file))
                .filter(Boolean)
            : [],
        }
      : null,
    validation: validation
      ? {
          result: validation.validated === true ? "PASS" : "FAIL",
          tests_run: typeof validation.tests_run === "number" ? validation.tests_run : null,
          tests_passed: typeof validation.tests_passed === "number" ? validation.tests_passed : null,
          bug_reproduced_before_patch: null,
          bug_reproduces_after_patch: validation.original_failure_resolved === false,
          duration_seconds:
            typeof validation.duration_seconds === "number" ? validation.duration_seconds : 0,
          output: stringValue(validation.test_stdout) || stringValue(validation.test_stderr),
          rejection_reason: validation.validated === false ? incident.error_reason ?? null : null,
          finished_at: stringValue(validation.completed_at) || incident.updated_at,
        }
      : null,
    pull_request: incident.pr_url
      ? {
          number: incident.pr_number ?? null,
          url: incident.pr_url,
          branch: incident.git_branch ?? "",
          state: "open",
        }
      : null,
    timeline: (incident.timeline ?? []).map((event) => ({
      status: statusForUi(event.status),
      at: event.timestamp,
      message: event.message ?? null,
    })),
  };
}

// ---------------------------------------------------------------------------
// GitHub OAuth endpoints
// ---------------------------------------------------------------------------

/**
 * Navigate the browser to the GitHub OAuth authorisation page.
 * The backend generates the state parameter and the redirect URI.
 * This is a full-page navigation, not a fetch.
 */
export function startGitHubLogin(): void {
  window.location.href = `${BASE}/api/github/login`;
}

/** Returns the authenticated user's GitHub profile, or null if not signed in. */
export async function getGitHubUser(signal?: AbortSignal): Promise<GithubUser | null> {
  try {
    return await getJson<GithubUser>("/api/github/me", signal);
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes("401")) return null;
    throw err;
  }
}

export interface ApiRepository {
  id: number;
  owner: string;
  name: string;
  fullName: string;
  private: boolean;
  language: string;
  pushedAt: string;
  defaultBranch: string;
  description: string;
  htmlUrl: string;
  cloneUrl: string;
  stargazersCount: number;
}

export interface ReposResponse {
  repos: ApiRepository[];
  page: number;
  per_page: number;
}

export function getGitHubRepos(
  page = 1,
  signal?: AbortSignal,
): Promise<ReposResponse> {
  return getJson(`/api/github/repos?page=${page}&per_page=50`, signal);
}

export interface SelectedRepository {
  id: number;
  owner: string;
  name: string;
  fullName: string;
  defaultBranch: string;
}

export function getSelectedRepository(signal?: AbortSignal): Promise<{ repository: SelectedRepository | null }> {
  return getJson("/api/github/selection", signal);
}

export function selectGitHubRepository(repository: ApiRepository): Promise<{ repository: ApiRepository }> {
  return writeJson("/api/github/selection", "PUT", repository);
}

export interface Branch {
  name: string;
  sha: string;
  protected: boolean;
}

export function getRepoBranches(
  owner: string,
  repo: string,
  signal?: AbortSignal,
): Promise<{ branches: Branch[] }> {
  return getJson(
    `/api/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/branches`,
    signal,
  );
}

export interface Commit {
  sha: string;
  shortSha: string;
  message: string;
  author: string;
  authorEmail: string;
  date: string;
  htmlUrl: string;
}

export function getRepoCommits(
  owner: string,
  repo: string,
  branch?: string,
  signal?: AbortSignal,
): Promise<{ commits: Commit[] }> {
  const q = branch ? `?branch=${encodeURIComponent(branch)}` : "";
  return getJson(
    `/api/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/commits${q}`,
    signal,
  );
}

export interface FileEntry {
  name: string;
  path: string;
  type: "file" | "dir" | "symlink";
  size: number;
  sha: string;
  htmlUrl: string;
  downloadUrl: string | null;
}

export type ContentsResponse =
  | { type: "directory"; path: string; entries: FileEntry[] }
  | { type: "file"; name: string; path: string; size: number; sha: string; encoding: string; content: string | null; htmlUrl: string; downloadUrl: string | null };

export function getRepoContents(
  owner: string,
  repo: string,
  path = "",
  ref?: string,
  signal?: AbortSignal,
): Promise<ContentsResponse> {
  const params = new URLSearchParams();
  if (path) params.set("path", path);
  if (ref) params.set("ref", ref);
  const q = params.toString() ? `?${params}` : "";
  return getJson(
    `/api/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents${q}`,
    signal,
  );
}

export interface CommitDiff {
  sha: string;
  message: string;
  author: string | null;
  date: string | null;
  stats: { additions: number; deletions: number; total: number };
  files: Array<{
    filename: string;
    status: string;
    additions: number;
    deletions: number;
    changes: number;
    patch: string | null;
    previousFilename: string | null;
  }>;
}

export function getCommitDiff(
  owner: string,
  repo: string,
  sha: string,
  signal?: AbortSignal,
): Promise<CommitDiff> {
  return getJson(
    `/api/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/diff?sha=${encodeURIComponent(sha)}`,
    signal,
  );
}

export function githubLogout(): Promise<{ status: string }> {
  return deleteJson("/api/github/logout");
}

export interface RepositoryAnalysis {
  repository: string;
  status: "queued" | "processing" | "ready" | "failed";
  result?: {
    language?: string;
    dockerfile_present?: boolean;
    dockerfile_generated?: boolean;
    build?: { passed: boolean };
    health?: { healthy: boolean; path?: string; status_code?: number; error?: string };
    resources?: Record<string, string>;
    logs?: string;
    error?: string;
  } | null;
}

export function getRepositoryAnalysis(
  repository: string,
  githubLogin: string,
  signal?: AbortSignal,
): Promise<RepositoryAnalysis> {
  const query = new URLSearchParams({ repository, github_login: githubLogin });
  return getJson(`/api/github/analysis?${query}`, signal);
}
