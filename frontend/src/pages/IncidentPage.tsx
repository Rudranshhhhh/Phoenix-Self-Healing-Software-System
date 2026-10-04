import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import type { Incident } from "../types/incident";
import { useIncident, useIncidentList } from "../hooks/useIncidentList";
import { useNow } from "../hooks/useNow";
import { useSession } from "../state/SessionContext";
import { AppHeader } from "../components/chrome/AppHeader";
import { PipelineArc } from "../components/phoenix/PipelineArc";
import { SectionBox } from "../components/incidents/SectionBox";
import { StatusBadge } from "../components/incidents/StatusBadge";
import { TracebackBox } from "../components/incidents/TracebackBox";
import { PatchBox, PendingLine, PullRequestBox, RootCauseBox, ValidationBox } from "../components/incidents/DetailSections";
import { IncidentSidebar } from "../components/incidents/IncidentSidebar";
import { SHOW_REJECTED } from "../lib/flags";
import { since } from "../lib/format";
import { blamedFrame, isActive, stageClock, stageStartMs } from "../lib/incident";
import { REPO } from "../lib/repo";

function SourceMeta({ incident, branch }: { incident: Incident; branch: string }) {
  const { source } = incident;
  const mono = "font-mono text-[12.5px] text-body";
  return (
    <span>
      {source.type === "github_actions" ? (
        source.workflow_run_url ? (
          <>
            Found in a{" "}
            <a
              href={source.workflow_run_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-ink underline underline-offset-[3px]"
            >
              CI run
            </a>{" "}
            on {branch}
          </>
        ) : (
          <>Found in CI on {branch}</>
        )
      ) : (
        <>
          Found in container <span className={mono}>{source.container ?? "unknown"}</span>
        </>
      )}
      {source.commit_sha && (
        <>
          {" "}at commit <span className={mono}>{source.commit_sha.slice(0, 7)}</span>
        </>
      )}
      , updated {since(incident.updated_at)}.
    </span>
  );
}

function IncidentBody({
  incident,
  branch,
  repoName,
  now,
}: {
  incident: Incident;
  branch: string;
  repoName: string;
  now: number;
}) {
  const blame = blamedFrame(incident.error);
  const clock = isActive(incident.status)
    ? stageClock(now - stageStartMs(incident.status, incident.timeline, incident.updated_at))
    : undefined;
  const openedAt = incident.timeline.find((e) => e.status === "pr_opened")?.at ?? null;

  return (
    <>
      <h1 className="mb-2.5 text-[22px] font-normal leading-[1.3] text-body [overflow-wrap:anywhere] sm:text-[28px]">
        <span className="font-semibold text-ink">{incident.error.exception_type}:</span> {incident.error.message}
        {" "}
        <span className="font-dot font-bold text-muted">{incident.id}</span>
      </h1>

      <div className="mb-5 flex flex-wrap items-center gap-x-3.5 gap-y-2.5 text-[14px] text-muted">
        <StatusBadge status={incident.status} />
        <SourceMeta incident={incident} branch={branch} />
      </div>

      <PipelineArc status={incident.status} incidentId={incident.id} detail={clock} repo={{ name: repoName, branch }} />

      <div className="mt-5 flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 grow-[999] basis-[560px] flex-col gap-4">
          <SectionBox
            title="Error"
            meta={blame ? `Blamed frame: ${blame.file}, line ${blame.line}` : undefined}
          >
            <TracebackBox error={incident.error} />
          </SectionBox>
          {incident.diagnosis && <RootCauseBox diagnosis={incident.diagnosis} />}
          {incident.patch && <PatchBox patch={incident.patch} />}
          {(incident.validation || incident.status === "validating") && (
            <ValidationBox validation={incident.validation} />
          )}
          {incident.pull_request && (
            <PullRequestBox
              pr={incident.pull_request}
              title={incident.patch?.summary ?? null}
              openedAt={openedAt}
              branch={branch}
            />
          )}
          <PendingLine status={incident.status} />
        </div>
        <IncidentSidebar incident={incident} branch={branch} now={now} />
      </div>
    </>
  );
}

export default function IncidentPage() {
  const { id = "" } = useParams();
  const { user, repo: sessionRepo } = useSession();
  const list = useIncidentList();
  const { incident, error, loading } = useIncident(id || null);
  const repo = useMemo(
    () => sessionRepo ?? { owner: REPO.owner, name: REPO.name, defaultBranch: REPO.branch },
    [sessionRepo],
  );
  const now = useNow(incident !== null && isActive(incident.status));
  const hidden = incident?.status === "rejected" && !SHOW_REJECTED;

  return (
    <div className="min-h-screen">
      <AppHeader
        owner={repo.owner}
        repo={repo.name}
        branch={repo.defaultBranch}
        release="9c41ab7"
        live={!list.loading && list.error === null}
        user={user?.login}
      />
      <main className="mx-auto max-w-[1200px] px-4 pb-12 pt-7 sm:px-6">
        <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-2 text-[14px] text-muted">
          <Link to="/app" className="text-ink underline underline-offset-[3px]">
            Incidents
          </Link>
          <span aria-hidden>/</span>
          <span className="font-dot text-[15px] font-bold text-ink">{id}</span>
        </nav>

        {!incident ? (
          <p className="text-[14px] text-muted">
            {loading || !error ? "Loading…" : `Couldn't load ${id}: ${error.message}. Retrying…`}
          </p>
        ) : hidden ? (
          <div className="rounded-box border border-line bg-surface px-6 py-12 text-center">
            <p className="text-[15px] font-semibold text-ink">This incident isn't shown.</p>
            <p className="mt-1 text-[14px] text-muted">Phoenix's fix didn't pass validation, so no pull request was opened.</p>
            <Link to="/app" className="mt-4 inline-block text-[14px] text-ink underline underline-offset-[3px]">
              Back to incidents
            </Link>
          </div>
        ) : (
          <>
            {error && <p className="mb-3 text-[13px] text-muted">Connection lost, retrying…</p>}
            <IncidentBody incident={incident} branch={repo.defaultBranch} repoName={repo.name} now={now} />
          </>
        )}
      </main>
    </div>
  );
}
