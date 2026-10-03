import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useIncidentList } from "../hooks/useIncidentList";
import { useSession } from "../state/SessionContext";
import { findRepository } from "../mock/repos";
import { AppHeader } from "../components/chrome/AppHeader";
import { GithubMark } from "../components/brand/Wordmark";
import { IncidentList } from "../components/dashboard/IncidentPanel";
import { Label, SectionRule } from "../components/ui/Primitives";

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
    return sessionRepo ?? { owner: "phoenix-labs", name: "orbital-checkout", defaultBranch: "main" };
  }, [params.owner, params.repo, sessionRepo]);

  const isDemo = !sessionRepo && !params.owner;

  return (
    <div className="min-h-screen">
      <AppHeader
        owner={repo.owner}
        repo={repo.name}
        branch={repo.defaultBranch}
        release="9c41ab7"
        live
        user={user?.login}
      />

      <main className="mx-auto max-w-[1420px] space-y-8 px-4 py-7 sm:px-6 sm:py-9">
        {isDemo && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-ash-800 bg-ash-925 px-4 py-3">
            <Label className="text-sodium/80">Demo workspace</Label>
            <Link
              to="/connect"
              className="ml-auto inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-sodium hover:underline"
            >
              <GithubMark size={12} />
              Connect
            </Link>
          </div>
        )}

        {/* -- incidents ------------------------------------------------ */}
        <section>
          <div className="mb-4 flex flex-wrap items-center gap-4">
            <SectionRule className="flex-1">Incidents</SectionRule>
          </div>
          <IncidentList {...incidentList} />
        </section>
      </main>
    </div>
  );
}
