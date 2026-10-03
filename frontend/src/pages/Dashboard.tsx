import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ServiceProcess } from "../types/phoenix";
import { useEngine } from "../hooks/useEngine";
import { useIncidentList } from "../hooks/useIncidentList";
import { engine } from "../mock/engine";
import { useSession } from "../state/SessionContext";
import { findRepository } from "../mock/repos";
import { cn } from "../lib/cn";
import { AppHeader } from "../components/chrome/AppHeader";
import { GithubMark } from "../components/brand/Wordmark";
import { MemoryFootnote, MetricStrip } from "../components/dashboard/MetricStrip";
import { ProcessTable } from "../components/dashboard/ProcessTable";
import { EventFeed, FailurePanel } from "../components/dashboard/Panels";
import { IncidentList } from "../components/dashboard/IncidentPanel";
import { Trend } from "../components/charts/Chart";
import { Label, SectionRule } from "../components/ui/Primitives";

// ---------------------------------------------------------------------------

const SERIES = [
  { key: "cpu", label: "CPU", unit: "%", domain: [0, 100] as [number, number], warn: 70, color: "var(--color-sodium)" },
  { key: "memory", label: "Memory", unit: "%", domain: [0, 100] as [number, number], warn: 75, color: "var(--color-iris)" },
  { key: "p95", label: "p95 latency", unit: "ms", domain: undefined, warn: 400, color: "var(--color-bone-2)" },
  { key: "errorRate", label: "Error rate", unit: "%", domain: undefined, warn: 1, color: "var(--color-brick)" },
] as const;

/**
 * One sentence about the process, in English, derived from the samples. Says
 * the specific thing that is true right now rather than a generic status word.
 */
function verdict(p: ServiceProcess): { text: string; tone: string } {
  const h = p.history;
  const last = h[h.length - 1];
  const earlier = h[Math.max(0, h.length - 25)];

  if (last.errorRate > 5) {
    return {
      text: `${p.name} is failing ${last.errorRate.toFixed(1)}% of requests. The traceback is in the incident list below.`,
      tone: "text-brick",
    };
  }
  const climb = last.memory - earlier.memory;
  if (climb > 8) {
    return {
      text: `Memory on ${p.name} has climbed ${climb.toFixed(0)} points in the last 40 seconds and is not coming back down.`,
      tone: "text-sodium",
    };
  }
  if (last.cpu > 80) {
    return {
      text: `${p.name} is pinned at ${last.cpu.toFixed(0)}% of one core. Requests are queuing behind it.`,
      tone: "text-sodium",
    };
  }
  if (last.p95 > 400) {
    return {
      text: `${p.name} is answering, but the slowest 5% of requests take ${Math.round(last.p95)}ms.`,
      tone: "text-sodium",
    };
  }
  return {
    text: `${p.name} is healthy. ${Math.round(last.rpm).toLocaleString()} requests a minute, ${last.p95.toFixed(0)}ms at p95, nothing thrown in this window.`,
    tone: "text-jade",
  };
}

// ---------------------------------------------------------------------------

export default function Dashboard() {
  const params = useParams();
  const { user, repo: sessionRepo } = useSession();
  const { services, incidents, feed, activeFaults } = useEngine();
  const incidentList = useIncidentList();

  const [selectedId, setSelectedId] = useState("web");
  const [seriesKey, setSeriesKey] = useState<(typeof SERIES)[number]["key"]>("cpu");

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
  const selected = services.find((s) => s.id === selectedId) ?? services[0];
  const series = SERIES.find((s) => s.key === seriesKey) ?? SERIES[0];
  const status = verdict(selected);
  const needsReview = incidents.filter(
    (i) => i.stage === "awaiting_review" || i.stage === "open",
  ).length;

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
            <p className="text-[13.5px] text-bone-2">
              These are simulated processes so you can see the whole flow. Connect your own repository to
              watch a real one.
            </p>
            <Link
              to="/connect"
              className="ml-auto inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-sodium hover:underline"
            >
              <GithubMark size={12} />
              Connect
            </Link>
          </div>
        )}

        {/* -- the sentence, then the figures --------------------------- */}
        <section>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <Label>Right now</Label>
              <p className={cn("mt-2 max-w-[58rem] text-[17px] leading-snug", status.tone)}>
                {status.text}
              </p>
            </div>
            <MemoryFootnote process={selected} />
          </div>

          <div className="mt-5">
            <MetricStrip process={selected} />
          </div>
        </section>

        {/* -- trend ---------------------------------------------------- */}
        <section className="overflow-hidden rounded-lg border border-ash-800 bg-ash-900">
          <div className="flex flex-wrap items-center gap-x-1 gap-y-2 border-b border-ash-800 bg-ash-925 px-4 py-2">
            {SERIES.map((s) => (
              <button
                key={s.key}
                onClick={() => setSeriesKey(s.key)}
                className={cn(
                  "relative px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
                  s.key === seriesKey ? "text-sodium" : "text-bone-4 hover:text-bone-2",
                )}
              >
                {s.label}
                {s.key === seriesKey && <span className="absolute inset-x-2 -bottom-px h-px bg-sodium" />}
              </button>
            ))}
            <span className="ml-auto pr-1 font-mono text-[10.5px] text-bone-4">
              {selected.name} · last 96 seconds
            </span>
          </div>

          <div className="px-4 pb-3 pt-5">
            <Trend
              values={selected.history.map((s) => s[series.key])}
              color={series.color}
              unit={series.unit}
              threshold={series.warn}
              domain={series.domain}
            />
            <div className="ml-12 mt-2 flex items-center justify-between font-mono text-[10px] text-bone-4">
              <span>−96s</span>
              <span>1.5s samples</span>
              <span>now</span>
            </div>
          </div>
        </section>

        {/* -- processes and feed --------------------------------------- */}
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_23rem]">
          <div>
            <SectionRule className="mb-4">Processes reporting</SectionRule>
            <ProcessTable processes={services} selected={selected.id} onSelect={setSelectedId} />
            <p className="mt-3 font-mono text-[11px] text-bone-4">
              Every process that called phoenix.init in this release. Select one to change the figures above.
            </p>
          </div>

          <div className="flex min-h-[22rem] flex-col xl:min-h-0">
            <SectionRule className="mb-4">Live from the reporter</SectionRule>
            <div className="min-h-0 flex-1">
              <EventFeed entries={feed} />
            </div>
          </div>
        </section>

        {/* -- incidents ------------------------------------------------ */}
        <section>
          <div className="mb-4 flex flex-wrap items-center gap-4">
            <SectionRule className="flex-1">Incidents</SectionRule>
            {needsReview > 0 && (
              <span className="font-mono text-[11px] text-sodium">
                {needsReview} waiting on you
              </span>
            )}
          </div>
          <IncidentList {...incidentList} />
        </section>

        {/* -- demo controls -------------------------------------------- */}
        <FailurePanel
          active={activeFaults}
          onInject={(kind) => engine.inject(kind)}
          onClear={() => engine.clearFaults()}
        />

        <p className="pb-6 font-mono text-[11px] text-bone-4">
          Phoenix has opened 3 pull requests against {repo.owner}/{repo.name}. You merged 2.
        </p>
      </main>
    </div>
  );
}
