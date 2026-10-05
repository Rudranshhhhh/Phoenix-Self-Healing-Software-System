import type { Incident, IncidentListResponse } from "../types/incident";
import type { GithubUser } from "../types/phoenix";

// ---------------------------------------------------------------------------
// Phoenix API client. In dev BASE is empty, so requests go to /api on the
// Vite server and its proxy forwards them to phoenix-api on port 8000.
// ---------------------------------------------------------------------------

const BASE: string = import.meta.env.VITE_API_URL ?? "";

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

// ---------------------------------------------------------------------------
// Existing incident endpoints (unchanged)
// ---------------------------------------------------------------------------

export function getIncidents(signal?: AbortSignal): Promise<IncidentListResponse> {
  return getJson("/api/incidents?page_size=100", signal);
}

export function getIncident(id: string, signal?: AbortSignal): Promise<Incident> {
  return getJson(`/api/incidents/${encodeURIComponent(id)}`, signal);
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
