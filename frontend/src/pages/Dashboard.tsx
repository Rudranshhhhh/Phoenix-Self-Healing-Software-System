import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useIncident, useIncidentList } from "../hooks/useIncidentList";
import { useSession } from "../state/SessionContext";
import { findRepository } from "../mock/repos";
import { AppHeader } from "../components/chrome/AppHeader";
import { GithubMark } from "../components/brand/Wordmark";
import { IncidentRows } from "../components/incidents/IncidentRows";
import { SHOW_REJECTED } from "../lib/flags";
import { LiveHero } from "../components/incidents/LiveHero";
import { isActive } from "../lib/incident";
import { REPO } from "../lib/repo";
import {
  getRepoBranches,
  getRepoCommits,
  getRepoContents,
  getRepositoryAnalysis,
} from "../api/phoenix";
import { usePolling } from "../hooks/usePolling";

const HERO_FRESH_MS = 10 * 60 * 1000;

export default function Dashboard() {
  const params = useParams();
  const { repo: sessionRepo, user } = useSession();
  const repositoryName = sessionRepo ? `${sessionRepo.owner}/${sessionRepo.name}` : undefined;
  const incidentList = useIncidentList(repositoryName);
  const analysisFetcher = useCallback(
    (signal: AbortSignal) =>
      sessionRepo && user
        ? getRepositoryAnalysis(repositoryName!, user.login, signal)
        : Promise.reject(new Error("No connected repository")),
    [repositoryName, sessionRepo, user],
  );
  const analysis = usePolling(
    analysisFetcher,
    5000,
    Boolean(sessionRepo && user),
  );

  // A repository from the URL wins, then the one picked on the connect screen,
  // then the demo workspace so /app is never a dead end.
  const repo = useMemo(() => {
    if (params.owner && params.repo) {
      return (
        findRepository(params.owner, params.repo) ?? {
          owner: params.owner,
          name: params.repo,
          defaultBranch: "main",
        }
      );
    }
    return sessionRepo ?? { owner: REPO.owner, name: REPO.name, defaultBranch: REPO.branch };
  }, [params.owner, params.repo, sessionRepo]);

  const isDemo = !sessionRepo && !params.owner;
  const intelligenceEnabled = Boolean(user && !isDemo);
  const [treePath, setTreePath] = useState("");
  const branchesFetcher = useCallback(
    (signal: AbortSignal) => getRepoBranches(repo.owner, repo.name, signal),
    [repo.owner, repo.name],
  );
  const commitsFetcher = useCallback(
    (signal: AbortSignal) => getRepoCommits(repo.owner, repo.name, repo.defaultBranch, signal),
    [repo.owner, repo.name, repo.defaultBranch],
  );
  const contentsFetcher = useCallback(
    (signal: AbortSignal) => getRepoContents(repo.owner, repo.name, treePath, repo.defaultBranch, signal),
    [repo.owner, repo.name, repo.defaultBranch, treePath],
  );
  const branches = usePolling(branchesFetcher, 30000, intelligenceEnabled);
  const commits = usePolling(commitsFetcher, 15000, intelligenceEnabled);
  const contents = usePolling(contentsFetcher, 30000, intelligenceEnabled);
  const { incidents, loading, error } = incidentList;
  const visible = useMemo(
    () => (SHOW_REJECTED ? incidents : incidents.filter((i) => i.status !== "rejected")),
    [incidents],
  );
  const validatedCount = incidents.filter((incident) => incident.validation_result === "PASS").length;
  const pullRequestCount = incidents.filter((incident) => Boolean(incident.pr_url)).length;
  // The hero follows the most recently updated incident Phoenix is still working on,
  // if it changed in the last 10 minutes; otherwise the most recent incident overall.
  // Stops a stale "Detected 3h ago" incident from looking live.
  const hero = useMemo(() => {
    const now = Date.now();
    const live = visible.find(
      (i) => isActive(i.status) && now - new Date(i.updated_at).getTime() < HERO_FRESH_MS,
    );
    return live ?? visible[0] ?? null;
  }, [visible]);
  const heroDetail = useIncident(hero?.id ?? null).incident;

  return (
    <div className="min-h-screen">
      <AppHeader
        owner={repo.owner}
        repo={repo.name}
        branch={repo.defaultBranch}
        live={!incidentList.loading && incidentList.error === null}
      />

      <main className="mx-auto max-w-[1200px] px-4 pb-12 pt-7 sm:px-6">
        {isDemo && (
          <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-box border border-line bg-surface px-4 py-3 text-[13px]">
            <span className="text-muted">Demo workspace</span>
            <Link
              to="/connect"
              className="ml-auto inline-flex items-center gap-1.5 font-medium text-ink underline-offset-2 hover:underline"
            >
              <GithubMark size={12} />
              Connect a repository
            </Link>
          </div>
        )}

        <h1 className="text-[24px] font-semibold leading-tight text-ink">Incidents</h1>
        <p className="mb-4 mt-1 text-[14px] text-muted">
          Failures on {repo.defaultBranch} that Phoenix is handling.
        </p>

        {analysis.data && (
          <section className="mb-6 rounded-box border border-line bg-surface px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-[16px] font-semibold text-ink">Runtime analysis</h2>
                <p className="mt-1 text-[13px] text-muted">
                  {analysis.data.status === "queued" && "Waiting for the local Docker agent…"}
                  {analysis.data.status === "processing" && "Building and checking the repository locally…"}
                  {analysis.data.status === "ready" && "Analysis completed from Docker Desktop telemetry."}
                  {analysis.data.status === "failed" && "Analysis failed; inspect the agent logs for details."}
                </p>
              </div>
              <span className="rounded-box border border-line bg-subtle px-2.5 py-1 text-[12px] text-body">
                {analysis.data.status}
              </span>
            </div>
            {analysis.data.result && (
              <div className="mt-4 grid gap-3 text-[13px] sm:grid-cols-2 lg:grid-cols-4">
                <span className="rounded-box border border-line bg-subtle px-3 py-2">
                  Runtime: {analysis.data.result.language ?? "unknown"}
                </span>
                <span className="rounded-box border border-line bg-subtle px-3 py-2">
                  Dockerfile: {analysis.data.result.dockerfile_generated ? "generated" : "existing"}
                </span>
                <span className="rounded-box border border-line bg-subtle px-3 py-2">
                  Build: {analysis.data.result.build?.passed ? "passed" : "failed"}
                </span>
                <span className="rounded-box border border-line bg-subtle px-3 py-2">
                  Health: {analysis.data.result.health?.healthy
                    ? `${analysis.data.result.health.path} · HTTP ${analysis.data.result.health.status_code}`
                    : `failed${analysis.data.result.health?.error ? ` · ${analysis.data.result.health.error}` : ""}`}
                </span>
                <span className="rounded-box border border-line bg-subtle px-3 py-2">
                  CPU: {analysis.data.result.resources?.["CPUPerc"] ?? "unavailable"}
                </span>
                <span className="rounded-box border border-line bg-subtle px-3 py-2">
                  Memory: {analysis.data.result.resources?.["MemUsage"] ?? "unavailable"}
                </span>
              </div>
            )}
            {analysis.data.result?.logs && (
              <pre className="mt-4 max-h-40 overflow-auto rounded-box bg-black/90 p-3 text-[11px] leading-5 text-white">
                {analysis.data.result.logs}
              </pre>
            )}
            {analysis.data.result?.error && (
              <p className="mt-3 break-words text-[13px] text-muted">
                Agent error: {analysis.data.result.error}
              </p>
            )}
            {analysis.error && <p className="mt-3 text-[13px] text-muted">Analysis unavailable; retrying…</p>}
          </section>
        )}

        {intelligenceEnabled && (
          <section className="mb-6 rounded-box border border-line bg-surface px-5 py-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-[16px] font-semibold text-ink">Repository intelligence</h2>
                <p className="mt-1 text-[13px] text-muted">
                  Live metadata from GitHub for {repo.owner}/{repo.name}.
                </p>
              </div>
              <a
                href={`https://github.com/${repo.owner}/${repo.name}`}
                target="_blank"
                rel="noreferrer"
                className="text-[13px] font-medium text-ink underline-offset-2 hover:underline"
              >
                Open on GitHub
              </a>
            </div>
            <div className="mt-4 grid gap-3 text-[13px] sm:grid-cols-3">
              <span className="rounded-box border border-line bg-subtle px-3 py-2">
                Branches: {branches.data?.branches.length ?? "loading…"}
              </span>
              <span className="rounded-box border border-line bg-subtle px-3 py-2">
                Root entries: {contents.data?.type === "directory" ? contents.data.entries.length : "loading…"}
              </span>
              <span className="rounded-box border border-line bg-subtle px-3 py-2">
                Latest push: {commits.data?.commits[0]?.date
                  ? new Date(commits.data.commits[0].date).toLocaleString()
                  : "loading…"}
              </span>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="rounded-box border border-line bg-subtle p-3">
                <h3 className="text-[13px] font-semibold text-ink">Latest commits</h3>
                <ul className="mt-2 space-y-2">
                  {(commits.data?.commits ?? []).slice(0, 5).map((commit) => (
                    <li key={commit.sha} className="flex items-start gap-2 text-[12px]">
                      <code className="shrink-0 text-muted">{commit.shortSha}</code>
                      <a
                        href={commit.htmlUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="min-w-0 truncate text-body hover:text-ink"
                        title={commit.message}
                      >
                        {commit.message}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-box border border-line bg-subtle p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="truncate text-[13px] font-semibold text-ink">
                    {treePath || "Root"} · {repo.defaultBranch}
                  </h3>
                  {treePath && (
                    <button
                      type="button"
                      onClick={() => setTreePath(treePath.split("/").slice(0, -1).join("/"))}
                      className="shrink-0 text-[12px] text-muted underline-offset-2 hover:text-ink hover:underline"
                    >
                      Up
                    </button>
                  )}
                </div>
                <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                  {(contents.data?.type === "directory" ? contents.data.entries : []).map((entry) => (
                    <li key={entry.path} className="truncate text-[12px] text-body">
                      {entry.type === "dir" ? (
                        <button
                          type="button"
                          onClick={() => setTreePath(entry.path)}
                          className="text-left hover:text-ink hover:underline"
                        >
                          <span className="mr-1 text-muted">▸</span>
                          {entry.name}
                        </button>
                      ) : (
                        <span>
                          <span className="mr-1 text-muted">·</span>
                          {entry.name}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            {(branches.error || commits.error || contents.error) && (
              <p className="mt-3 text-[12px] text-muted">
                Some GitHub repository details could not be loaded; retrying automatically.
              </p>
            )}
          </section>
        )}

        {loading ? (
          <p className="text-[14px] text-muted">Loading incidents…</p>
        ) : error && incidents.length === 0 ? (
          <div className="rounded-box border border-line bg-surface px-6 py-12 text-center">
            <p className="text-[15px] text-body">Can't reach the Phoenix API. Is phoenix-api running on port 8000?</p>
            <p className="mt-2 font-mono text-[12px] text-muted">{error.message}</p>
          </div>
        ) : (
          <>
            {!hero && (
              <div className="rounded-box border border-line bg-surface px-6 py-10">
                <h2 className="text-[17px] font-semibold text-ink">Repository connected</h2>
                <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-body">
                  Phoenix is watching {repo.owner}/{repo.name}. No incidents have been reported yet.
                  When GitHub Actions sends a failure, the local Docker agent will analyze it, validate a
                  fix, and report the resulting pull request here.
                </p>
                <div className="mt-5 grid gap-3 text-[13px] text-muted sm:grid-cols-3">
                  <span className="rounded-box border border-line bg-subtle px-3 py-2">
                    Incidents: {incidents.length}
                  </span>
                  <span className="rounded-box border border-line bg-subtle px-3 py-2">
                    Validated fixes: {validatedCount}
                  </span>
                  <span className="rounded-box border border-line bg-subtle px-3 py-2">
                    Pull requests: {pullRequestCount}
                  </span>
                </div>
              </div>
            )}
            <LiveHero
              summary={hero}
              incident={heroDetail && hero && heroDetail.id === hero.id ? heroDetail : null}
              branch={repo.defaultBranch}
              repoName={repo.name}
            />
            {error && <p className="mb-3 text-[13px] text-muted">Connection lost, retrying…</p>}
            {visible.length > 0 && <IncidentRows incidents={visible} />}
          </>
        )}
      </main>
    </div>
  );
}
