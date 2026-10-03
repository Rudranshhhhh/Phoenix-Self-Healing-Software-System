import { useState } from "react";
import type { ReactNode } from "react";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import type {
  Diagnosis,
  IncidentSource,
  IncidentSummary,
  Patch,
  PullRequest,
  SourceType,
  Validation,
} from "../../types/incident";
import { useIncident } from "../../hooks/useIncidentList";
import { since } from "../../lib/format";
import { statusLabel, statusTone } from "../../lib/status";
import type { ChipTone } from "../../lib/status";
import { cn } from "../../lib/cn";
import { Chip, Label, SectionRule } from "../ui/Primitives";
import { DiffView, TracebackView } from "../code/Traceback";
import { Steps } from "./Steps";
import { SHOW_REJECTED } from "../../lib/flags";

// ============================================================================
// The incident list, read from the Phoenix API.
// ============================================================================

const SOURCE_LABEL: Record<SourceType, string> = {
  github_actions: "CI",
  docker_runtime: "Runtime",
};

/** The row's left bar takes the colour of its status chip. */
const TONE_BAR: Record<ChipTone, string> = {
  brick: "bg-brick",
  iris: "bg-iris",
  sodium: "bg-sodium",
  jade: "bg-jade",
  neutral: "bg-bone-4",
};

const MUTED = "font-mono text-[11px] text-bone-4";

// ---------------------------------------------------------------------------
// One incident, expanded. Each section appears once its data exists, so a
// live incident fills in from the top down as the poll picks up new stages.
// ---------------------------------------------------------------------------

const yesNo = (value: boolean) => (value ? "Yes" : "No");

const PR_TONE: Record<PullRequest["state"], ChipTone> = {
  open: "jade",
  merged: "iris",
  closed: "neutral",
};

function Pending({ children }: { children: string }) {
  return <p className={cn(MUTED, "mt-3")}>{children}</p>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <SectionRule>{title}</SectionRule>
      {children}
    </section>
  );
}

function SourceMeta({ source }: { source: IncidentSource }) {
  return (
    <p className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-bone-4">
      {source.workflow_run_url ? (
        <a
          href={source.workflow_run_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-bone-3 underline decoration-ash-700 underline-offset-2 hover:text-bone"
        >
          CI run <ArrowUpRight size={11} />
        </a>
      ) : source.container ? (
        <span>Container {source.container}</span>
      ) : null}
      {source.commit_sha && <span>commit {source.commit_sha.slice(0, 7)}</span>}
    </p>
  );
}

function DiagnosisBody({ diagnosis }: { diagnosis: Diagnosis }) {
  const location =
    diagnosis.suspect_file &&
    `${diagnosis.suspect_file}${diagnosis.suspect_line !== null ? `:${diagnosis.suspect_line}` : ""}`;
  return (
    <div className="mt-3">
      <p className="text-[15px] leading-snug text-bone">{diagnosis.root_cause}</p>
      <p className="mt-2 max-w-3xl text-[13.5px] leading-relaxed text-bone-3">{diagnosis.explanation}</p>
      <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11.5px]">
        {location && <span className="text-sodium">{location}</span>}
        {diagnosis.confidence !== null && (
          <span className="text-bone-4">{Math.round(diagnosis.confidence * 100)}% confidence</span>
        )}
      </p>
      {diagnosis.context_files.length > 0 && (
        <div className="mt-3">
          <Label className="text-bone-4">Context read</Label>
          <ul className={cn(MUTED, "mt-1.5 space-y-0.5")}>
            {diagnosis.context_files.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PatchBody({ patch }: { patch: Patch }) {
  return (
    <div className="mt-3">
      <p className="text-[14px] text-bone-2">{patch.summary}</p>
      <p className={cn(MUTED, "mt-1.5")}>
        {patch.files_changed.length} {patch.files_changed.length === 1 ? "file" : "files"} changed:{" "}
        {patch.files_changed.join(", ")}
      </p>
      <div className="mt-3">
        <DiffView diff={patch.diff} />
      </div>
    </div>
  );
}

function ValidationBody({ validation }: { validation: Validation }) {
  const pass = validation.result === "PASS";
  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Chip tone={pass ? "jade" : "brick"}>{validation.result}</Chip>
        <span className="font-mono text-[12.5px] text-bone-2">
          {validation.tests_passed}/{validation.tests_run} tests passed
        </span>
        <span className={MUTED}>
          {validation.duration_seconds.toFixed(1)}s · finished {since(validation.finished_at)}
        </span>
      </div>

      {!pass && validation.rejection_reason && (
        <div className="mt-3 rounded-md border border-brick/35 bg-brick/8 px-4 py-3">
          <Label className="text-brick">Rejected</Label>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-bone">{validation.rejection_reason}</p>
        </div>
      )}

      <dl className="mt-3 grid gap-x-6 gap-y-1 font-mono text-[11.5px] sm:grid-cols-[auto_1fr]">
        <dt className="text-bone-4">Bug reproduced before patch</dt>
        <dd className="text-bone-2">{yesNo(validation.bug_reproduced_before_patch)}</dd>
        <dt className="text-bone-4">Bug still reproduces after patch</dt>
        <dd className={validation.bug_reproduces_after_patch ? "text-brick" : "text-bone-2"}>
          {yesNo(validation.bug_reproduces_after_patch)}
        </dd>
      </dl>

      <details className="group mt-4 rounded-md border border-ash-800 bg-ash-925">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2 font-mono text-[11px] text-bone-3 hover:text-bone [&::-webkit-details-marker]:hidden">
          <ChevronRight size={12} className="transition-transform duration-200 group-open:rotate-90" />
          Test output
        </summary>
        <pre className="mono-pane max-h-[320px] overflow-auto border-t border-ash-800 px-4 py-3 text-bone-3">
          {validation.output}
        </pre>
      </details>
    </div>
  );
}

function PullRequestBody({ pr }: { pr: PullRequest }) {
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
      <a
        href={pr.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[14px] text-bone underline decoration-ash-700 underline-offset-2 hover:decoration-bone-3"
      >
        Pull request #{pr.number} <ArrowUpRight size={13} />
      </a>
      <span className="font-mono text-[11.5px] text-bone-3">{pr.branch}</span>
      <Chip tone={PR_TONE[pr.state]}>{pr.state}</Chip>
    </p>
  );
}

export function Detail({ id }: { id: string }) {
  const { incident, error } = useIncident(id);

  if (!incident) {
    return (
      <div className="border-t border-ash-800 bg-ash-925 px-4 py-6 sm:px-6">
        <p className={MUTED}>{error ? `Couldn't load ${id}. Retrying…` : "Loading…"}</p>
      </div>
    );
  }

  const { status, diagnosis, patch, validation, pull_request } = incident;

  return (
    <div className="border-t border-ash-800 bg-ash-925 px-4 py-6 sm:px-6">
      {error && <p className={cn(MUTED, "mb-3")}>Connection lost, retrying…</p>}

      <Steps status={status} />

      <Section title="Error">
        <TracebackView error={incident.error} className="mt-3" />
        <SourceMeta source={incident.source} />
      </Section>

      {diagnosis ? (
        <Section title="Root cause">
          <DiagnosisBody diagnosis={diagnosis} />
        </Section>
      ) : status === "diagnosing" ? (
        <Section title="Root cause">
          <Pending>Diagnosing…</Pending>
        </Section>
      ) : null}

      {patch && (
        <Section title="Proposed patch">
          <PatchBody patch={patch} />
        </Section>
      )}

      {validation ? (
        <Section title="Validation">
          <ValidationBody validation={validation} />
        </Section>
      ) : status === "validating" ? (
        <Section title="Validation">
          <Pending>Running tests in the sandbox…</Pending>
        </Section>
      ) : null}

      {pull_request ? (
        <Section title="Pull request">
          <PullRequestBody pr={pull_request} />
        </Section>
      ) : status === "validated" ? (
        <Section title="Pull request">
          <Pending>Passed validation. No pull request yet.</Pending>
        </Section>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The list
// ---------------------------------------------------------------------------

export function IncidentList({
  incidents,
  error,
  loading,
}: {
  incidents: IncidentSummary[];
  error: Error | null;
  loading: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);

  if (loading) {
    return <p className={MUTED}>Loading incidents…</p>;
  }

  if (error && incidents.length === 0) {
    return (
      <div className="rounded-lg border border-ash-800 bg-ash-900 px-6 py-16 text-center">
        <p className="text-[15px] text-bone-2">
          Can't reach the Phoenix API. Is phoenix-api running on port 8000?
        </p>
        <p className="mt-2 font-mono text-[11.5px] text-bone-4">{error.message}</p>
      </div>
    );
  }

  const visible = SHOW_REJECTED ? incidents : incidents.filter((i) => i.status !== "rejected");

  if (visible.length === 0) {
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
    <div>
      {error && <p className={cn(MUTED, "mb-3")}>Connection lost, retrying…</p>}

      <ul className="overflow-hidden rounded-lg border border-ash-800">
        {visible.map((incident, i) => {
          const tone = statusTone(incident.status);
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
                <span aria-hidden className={cn("mt-1 h-8 w-[2px] shrink-0 rounded-xs", TONE_BAR[tone])} />

                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                    <span className="font-mono text-[13.5px] font-medium text-brick">
                      {incident.exception_type}
                    </span>
                    <span className="min-w-0 truncate font-mono text-[13px] text-bone-2">
                      {incident.message}
                    </span>
                  </span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-bone-4">
                    <span>{incident.id}</span>
                    <span>{SOURCE_LABEL[incident.source_type]}</span>
                    <span>updated {since(incident.updated_at)}</span>
                  </span>
                </span>

                <span className="flex shrink-0 items-center gap-3 pt-0.5">
                  <Chip tone={tone}>{statusLabel(incident.status)}</Chip>
                  <ChevronRight
                    size={15}
                    className={cn("text-bone-4 transition-transform duration-200", open_ && "rotate-90")}
                  />
                </span>
              </button>

              {open_ && <Detail id={incident.id} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
