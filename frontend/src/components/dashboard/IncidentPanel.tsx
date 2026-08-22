import { useEffect, useRef, useState } from "react";
import { ChevronRight, GitPullRequest, Sparkles, X } from "lucide-react";
import type { Incident, RepairStage, Severity } from "../../types/phoenix";
import { engine } from "../../mock/engine";
import { since } from "../../lib/format";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";
import { Chip, Label } from "../ui/Primitives";
import { DiffView, TracebackView } from "../code/Traceback";

// ============================================================================
// The incident list, and the repair a human has to sign off on.
// ============================================================================

const SEVERITY_BAR: Record<Severity, string> = {
  critical: "bg-brick",
  high: "bg-sodium",
  medium: "bg-bone-3",
  low: "bg-bone-4",
};

type ChipSpec = { tone: "neutral" | "sodium" | "brick" | "jade" | "iris"; text: string };

function stageChip(incident: Incident): ChipSpec {
  switch (incident.stage) {
    case "open":
      return { tone: "brick", text: "unrepaired" };
    case "reproducing":
      return { tone: "iris", text: "reproducing" };
    case "patching":
      return { tone: "iris", text: "writing patch" };
    case "testing":
      return { tone: "iris", text: "running tests" };
    case "awaiting_review":
      return { tone: "sodium", text: "needs your review" };
    case "pr_open":
      return { tone: "jade", text: `pr #${incident.fix?.prNumber ?? "—"}` };
    case "declined":
      return { tone: "neutral", text: "declined" };
    case "unfixable":
      return { tone: "neutral", text: "unfixable" };
  }
}

// ---------------------------------------------------------------------------
// Repair progress: four steps, named for what actually happens.
// ---------------------------------------------------------------------------

const STEPS: Array<{ stage: RepairStage; label: string; detail: string }> = [
  { stage: "reproducing", label: "Reproduce", detail: "clone at the failing commit, replay the frame" },
  { stage: "patching", label: "Patch", detail: "write the smallest change that stops it" },
  { stage: "testing", label: "Test", detail: "run the full suite against the patch" },
  { stage: "awaiting_review", label: "Review", detail: "hand it to you" },
];

const ORDER: RepairStage[] = ["open", "reproducing", "patching", "testing", "awaiting_review"];

function Steps({ stage }: { stage: RepairStage }) {
  const at = ORDER.indexOf(stage);
  return (
    <ol className="grid gap-px overflow-hidden rounded-md border border-ash-800 bg-ash-800 sm:grid-cols-4">
      {STEPS.map((step, i) => {
        const index = ORDER.indexOf(step.stage);
        const done = at > index;
        const current = at === index;
        return (
          <li key={step.stage} className="bg-ash-900 px-4 py-3">
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className={cn(
                  "grid h-4 w-4 shrink-0 place-items-center rounded-xs border font-mono text-[9px]",
                  done && "border-jade/50 bg-jade/12 text-jade",
                  current && "border-iris/60 bg-iris/12 text-iris",
                  !done && !current && "border-ash-700 text-bone-4",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "font-mono text-[12px]",
                  done ? "text-jade" : current ? "text-iris" : "text-bone-4",
                )}
              >
                {step.label}
              </span>
              {current && <span className="animate-caret text-iris">▌</span>}
            </span>
            <span className="mt-1.5 block text-[11.5px] leading-snug text-bone-4">{step.detail}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// One incident, expanded
// ---------------------------------------------------------------------------

function Detail({ incident, repo }: { incident: Incident; repo: string }) {
  const timers = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const [declined, setDeclined] = useState(false);

  useEffect(() => {
    const all = timers.current;
    return () => all.forEach(clearTimeout);
  }, []);

  const runRepair = () => {
    setDeclined(false);
    const beats: Array<[RepairStage, number]> = [
      ["reproducing", 0],
      ["patching", 1600],
      ["testing", 3400],
      ["awaiting_review", 5700],
    ];
    for (const [stage, at] of beats) {
      timers.current.push(setTimeout(() => engine.setStage(incident.id, stage), at));
    }
  };

  const openPr = () => {
    engine.setStage(incident.id, "pr_open", { prNumber: 1200 + Math.floor(incident.count % 90) });
  };

  const decline = () => {
    setDeclined(true);
    engine.setStage(incident.id, "declined");
  };

  const working =
    incident.stage === "reproducing" || incident.stage === "patching" || incident.stage === "testing";

  return (
    <div className="border-t border-ash-800 bg-ash-925 px-4 py-6 sm:px-6">
      {/* -- context ------------------------------------------------------ */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_15rem]">
        <div className="min-w-0">
          <Label>Captured traceback</Label>
          <TracebackView incident={incident} className="mt-3" />
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 self-start lg:grid-cols-1">
          {[
            ["Entry point", `${incident.request.method} ${incident.request.path}`],
            ["Response", incident.request.status === 0 ? "task failed" : String(incident.request.status)],
            ["Release", incident.request.releaseSha],
            ["Client", incident.request.userAgent],
            ["First seen", since(incident.firstSeen)],
            ["Events", `${incident.count} · ${incident.usersAffected} users`],
          ].map(([term, value]) => (
            <div key={term}>
              <dt className="ledger-label">{term}</dt>
              <dd className="tnum mt-1 truncate text-[12px] text-bone-2">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <hr className="rule my-6" />

      {/* -- repair ------------------------------------------------------- */}
      {incident.stage === "unfixable" ? (
        <div className="rounded-md border border-brick/25 bg-brick/6 p-5">
          <Label className="text-brick">Phoenix stopped here</Label>
          <p className="mt-2.5 max-w-[52rem] text-[14px] leading-relaxed text-bone-2">{incident.note}</p>
        </div>
      ) : incident.stage === "declined" || declined ? (
        <div className="flex flex-wrap items-center gap-4">
          <p className="text-[14px] text-bone-2">
            You declined this patch. The incident stays open and nothing was pushed.
          </p>
          <Button className="ml-auto" onClick={runRepair}>
            Try a different patch
          </Button>
        </div>
      ) : incident.stage === "open" ? (
        <div className="flex flex-wrap items-end gap-6">
          <div className="max-w-[40rem]">
            <Label>No repair attempted</Label>
            <p className="mt-2.5 text-[14px] leading-relaxed text-bone-2">
              Phoenix will clone <span className="font-mono text-[13px] text-bone">{repo}</span> at{" "}
              <span className="font-mono text-[13px] text-bone">{incident.request.releaseSha}</span> into a
              sandbox, replay this frame, and try to write a patch. Nothing is pushed until you read the diff.
            </p>
          </div>
          <Button tone="primary" size="lg" className="ml-auto" onClick={runRepair}>
            <Sparkles size={15} />
            Fix this
          </Button>
        </div>
      ) : working ? (
        <div>
          <Label className="text-iris">Repairing</Label>
          <div className="mt-3">
            <Steps stage={incident.stage} />
          </div>
        </div>
      ) : incident.fix ? (
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <Label className={incident.stage === "pr_open" ? "text-jade" : "text-sodium"}>
              {incident.stage === "pr_open" ? "Pull request open" : "Patch ready for review"}
            </Label>
            <Chip tone="jade">
              {incident.fix.testsPassed}/{incident.fix.testsRun} tests pass
            </Chip>
            <span className="font-mono text-[11.5px] text-bone-3">{incident.fix.branch}</span>
          </div>

          <h4 className="mt-4 font-sans text-[15.5px] font-medium tracking-normal text-bone">
            {incident.fix.summary}
          </h4>
          <p className="mt-2 max-w-[54rem] text-[14px] leading-relaxed text-bone-2">
            {incident.fix.reasoning}
          </p>

          <div className="mt-5">
            <DiffView hunks={incident.fix.hunks} />
          </div>

          {incident.stage === "awaiting_review" ? (
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button tone="primary" size="lg" onClick={openPr}>
                <GitPullRequest size={15} />
                Open pull request
              </Button>
              <Button tone="danger" size="lg" onClick={decline}>
                <X size={15} />
                Decline
              </Button>
              <span className="font-mono text-[11.5px] text-bone-4">
                Opening a pull request pushes {incident.fix.branch}. It does not merge.
              </span>
            </div>
          ) : (
            <div className="mt-5 flex flex-wrap items-center gap-3 rounded-md border border-jade/25 bg-jade/6 px-4 py-3">
              <GitPullRequest size={15} className="text-jade" />
              <span className="font-mono text-[12.5px] text-jade">
                #{incident.fix.prNumber} on {incident.fix.branch}
              </span>
              <span className="text-[13.5px] text-bone-2">
                Pushed to {repo}. Review and merge it in GitHub when you're ready.
              </span>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The list
// ---------------------------------------------------------------------------

export function IncidentList({ incidents, repo }: { incidents: Incident[]; repo: string }) {
  const [open, setOpen] = useState<string | null>(incidents[0]?.id ?? null);

  if (incidents.length === 0) {
    return (
      <div className="rounded-lg border border-ash-800 bg-ash-900 px-6 py-16 text-center">
        <p className="text-[15px] text-bone-2">Nothing has thrown since the reporter attached.</p>
        <p className="mt-2 text-[13.5px] text-bone-4">
          Incidents appear here the moment an unhandled exception reaches the reporter.
        </p>
      </div>
    );
  }

  return (
    <ul className="overflow-hidden rounded-lg border border-ash-800">
      {incidents.map((incident, i) => {
        const chip = stageChip(incident);
        const open_ = open === incident.id;
        return (
          <li key={incident.id} className={cn(i > 0 && "border-t border-ash-800")}>
            <button
              type="button"
              onClick={() => setOpen(open_ ? null : incident.id)}
              aria-expanded={open_}
              className={cn(
                "flex w-full items-start gap-4 px-4 py-4 text-left transition-colors sm:px-5",
                open_ ? "bg-ash-850" : "bg-ash-900 hover:bg-ash-850/70",
              )}
            >
              <span
                aria-hidden
                className={cn("mt-1 h-8 w-[2px] shrink-0 rounded-xs", SEVERITY_BAR[incident.severity])}
              />

              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                  <span className="font-mono text-[13.5px] font-medium text-brick">
                    {incident.exception}
                  </span>
                  <span className="min-w-0 truncate font-mono text-[13px] text-bone-2">
                    {incident.message}
                  </span>
                </span>
                <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-bone-4">
                  <span>{incident.id}</span>
                  <span>{incident.service}</span>
                  <span>
                    {incident.count} events · {incident.usersAffected} users
                  </span>
                  <span>last {since(incident.lastSeen)}</span>
                </span>
              </span>

              <span className="flex shrink-0 items-center gap-3 pt-0.5">
                <Chip tone={chip.tone}>{chip.text}</Chip>
                <ChevronRight
                  size={15}
                  className={cn("text-bone-4 transition-transform duration-200", open_ && "rotate-90")}
                />
              </span>
            </button>

            {open_ && <Detail incident={incident} repo={repo} />}
          </li>
        );
      })}
    </ul>
  );
}
