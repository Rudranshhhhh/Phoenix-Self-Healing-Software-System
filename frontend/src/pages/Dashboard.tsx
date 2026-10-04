import { useMemo } from "react";
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

const HERO_FRESH_MS = 10 * 60 * 1000;

export default function Dashboard() {
  const params = useParams();
  const { user, repo: sessionRepo } = useSession();
  const incidentList = useIncidentList();

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
  const { incidents, loading, error } = incidentList;
  const visible = useMemo(
    () => (SHOW_REJECTED ? incidents : incidents.filter((i) => i.status !== "rejected")),
    [incidents],
  );
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
        release="9c41ab7"
        live={!incidentList.loading && incidentList.error === null}
        user={user?.login}
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

        {loading ? (
          <p className="text-[14px] text-muted">Loading incidents…</p>
        ) : error && incidents.length === 0 ? (
          <div className="rounded-box border border-line bg-surface px-6 py-12 text-center">
            <p className="text-[15px] text-body">Can't reach the Phoenix API. Is phoenix-api running on port 8000?</p>
            <p className="mt-2 font-mono text-[12px] text-muted">{error.message}</p>
          </div>
        ) : (
          <>
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
