import { useState } from "react";
import type { Diagnosis, IncidentStatus, Patch, PullRequest, Validation } from "../../types/incident";
import { parseUnifiedDiff } from "../../lib/diff";
import { since } from "../../lib/format";
import { cn } from "../../lib/cn";
import { SectionBox } from "./SectionBox";
import { DiffBox, diffCounts } from "./DiffBox";
import { StatusIcon } from "./StatusIcon";

const ICON = {
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function Tick({ good }: { good: boolean }) {
  return (
    <svg {...ICON} width={14} height={14} strokeWidth={1.6}>
      {good ? <path d="M3.5 8.5l3 3 6-6.5" /> : <path d="M4 4l8 8M12 4l-8 8" />}
    </svg>
  );
}

function ResultIcon({ pass }: { pass: boolean }) {
  return (
    <svg {...ICON} width={22} height={22} strokeWidth={1.5}>
      <circle cx="8" cy="8" r="6.5" />
      {pass ? <path d="M5 8.2l2 2 4-4.2" /> : <path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" />}
    </svg>
  );
}

export function Chip({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-box border border-line bg-subtle px-[7px] font-mono text-[12px] leading-5 text-body [overflow-wrap:anywhere]">
      {children}
    </span>
  );
}

export function RootCauseBox({ diagnosis }: { diagnosis: Diagnosis }) {
  const location = diagnosis.suspect_file
    ? `${diagnosis.suspect_file}${diagnosis.suspect_line !== null ? `:${diagnosis.suspect_line}` : ""}`
    : null;
  const read = diagnosis.context_files.length;
  return (
    <SectionBox title="Root cause" meta="Found by Phoenix">
      <div className="p-4">
        <p className="mb-1.5 text-[16px] font-semibold leading-[1.4] text-ink">{diagnosis.root_cause}</p>
        <p className="mb-3.5 max-w-[72ch] text-[14px] leading-relaxed text-body">{diagnosis.explanation}</p>
        <div className="flex flex-wrap gap-x-7 gap-y-1.5 text-[13px] text-muted">
          {location && (
            <span>
              Location <span className="font-mono font-semibold text-body">{location}</span>
            </span>
          )}
          {diagnosis.confidence !== null && (
            <span>
              Confidence <span className="font-semibold text-body">{Math.round(diagnosis.confidence * 100)}%</span>
            </span>
          )}
          {read > 0 && (
            <span>
              Read <span className="font-semibold text-body">{read} {read === 1 ? "file" : "files"}</span>
            </span>
          )}
        </div>
      </div>
    </SectionBox>
  );
}

export function PatchBox({ patch }: { patch: Patch }) {
  const files = parseUnifiedDiff(patch.diff);
  const { add, del } = diffCounts(files);
  const what =
    patch.files_changed.length === 1 ? patch.files_changed[0] : `${patch.files_changed.length} files`;
  return (
    <SectionBox
      title="Proposed patch"
      meta={
        <>
          <span className="font-mono">{what}</span>
          {"  "}
          <span className="font-semibold text-pass">+{add}</span>{" "}
          <span className="font-semibold text-fail">−{del}</span>
        </>
      }
    >
      <p className="border-b border-line px-4 py-2.5 text-[14px] text-body">{patch.summary}</p>
      <DiffBox files={files} raw={patch.diff} />
    </SectionBox>
  );
}

/** `validation` null = tests are running right now. */
export function ValidationBox({ validation }: { validation: Validation | null }) {
  const [showOutput, setShowOutput] = useState(false);

  if (!validation) {
    return (
      <SectionBox title="Validation" meta="Running now">
        <div className="flex items-center gap-2.5 p-4 text-[14px] font-semibold text-ink">
          <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-ember" />
          Running the tests in a Docker sandbox
        </div>
      </SectionBox>
    );
  }

  const pass = validation.result === "PASS";
  const { tests_passed: passed, tests_run: run, bug_reproduced_before_patch: before } = validation;
  const counted = passed !== null && run !== null;
  // good: null = the pipeline didn't report it, so the row stays neutral (muted, no icon).
  const checks: { label: string; value: string; good: boolean | null }[] = [
    {
      label: "Tests passed",
      value: `${passed ?? "—"} of ${run ?? "—"}`,
      good: counted ? passed === run : null,
    },
    {
      label: "Bug reproduced before patch",
      value: before === null ? "Not checked" : before ? "Yes" : "No",
      good: before,
    },
    {
      label: "Bug still reproduces after patch",
      value: validation.bug_reproduces_after_patch ? "Yes" : "No",
      good: !validation.bug_reproduces_after_patch,
    },
  ];

  return (
    <SectionBox
      title="Validation"
      meta={`Docker sandbox, ${validation.duration_seconds.toFixed(1)}s, finished ${since(validation.finished_at)}`}
    >
      <div className="p-4">
        <div
          className={cn(
            "flex items-center gap-2.5 text-[20px] font-semibold leading-tight",
            pass ? "text-pass" : "text-fail",
          )}
        >
          <ResultIcon pass={pass} />
          {pass ? "Passed" : "Failed"}
        </div>
        <p className="mb-3 mt-1 text-[14px] text-muted">
          {passed ?? "—"} of {run ?? "—"} tests passed in the sandbox.
        </p>

        <dl>
          {checks.map((c) => (
            <div key={c.label} className="flex items-center justify-between gap-4 border-t border-line py-2 text-[14px]">
              <dt className="text-body">{c.label}</dt>
              <dd
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap font-semibold",
                  c.good === null ? "text-muted" : c.good ? "text-pass" : "text-fail",
                )}
              >
                {c.good !== null && <Tick good={c.good} />}
                {c.value}
              </dd>
            </div>
          ))}
        </dl>

        {!pass && validation.rejection_reason && (
          <div className="mt-3 rounded-box border border-[#FFCECB] bg-del-bg px-4 py-3 text-[14px] leading-relaxed text-body">
            <span className="font-semibold text-ink">Why Phoenix rejected this fix.</span>{" "}
            {validation.rejection_reason}
          </div>
        )}

        <div className="mt-3.5">
          <button
            type="button"
            aria-expanded={showOutput}
            onClick={() => setShowOutput((v) => !v)}
            className="inline-flex min-h-[44px] items-center rounded-box border border-line bg-surface px-3 text-[13px] font-medium text-body hover:bg-subtle sm:min-h-8"
          >
            {showOutput ? "Hide test output" : "Show test output"}
          </button>
          {showOutput && (
            <pre className="mt-2.5 max-h-[360px] overflow-auto rounded-box border border-line bg-code px-4 py-2 font-mono text-[12px] leading-5 text-body">
              {validation.output}
            </pre>
          )}
        </div>
      </div>
    </SectionBox>
  );
}

const PR_NOTE: Record<PullRequest["state"], string> = {
  open: "Waiting for review.",
  merged: "Merged.",
  closed: "Closed without merging.",
};

export function PullRequestBox({
  pr,
  title,
  openedAt,
  branch,
}: {
  pr: PullRequest;
  title: string | null;
  openedAt: string | null;
  branch: string;
}) {
  return (
    <SectionBox title="Pull request" meta={openedAt ? `Opened by Phoenix ${since(openedAt)}` : "Opened by Phoenix"}>
      <div className="flex items-start gap-2.5 p-4">
        <StatusIcon status="pr_opened" className="mt-1" />
        <div className="min-w-0">
          <a
            href={pr.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[16px] font-semibold text-ink underline underline-offset-[3px]"
          >
            {pr.number === null ? "Pull request" : `Pull request #${pr.number}`}
          </a>
          {title && <p className="mb-1.5 mt-0.5 text-[14px] text-body">{title}</p>}
          <div className="flex flex-wrap items-center gap-1.5 text-[13px] text-muted">
            <Chip>{pr.branch}</Chip>
            <span>into</span>
            <Chip>{branch}</Chip>
            <span>{PR_NOTE[pr.state]}</span>
          </div>
        </div>
      </div>
    </SectionBox>
  );
}

// What the page says while a stage has nothing to show yet. Ember only where Phoenix is acting.
// "validated" stays neutral: PR auto-open vs button is still an open team decision.
const PENDING: Partial<Record<IncidentStatus, { text: string; ember: boolean }>> = {
  detected: { text: "Diagnosis starts as soon as a worker is free.", ember: false },
  diagnosing: { text: "Phoenix is reading the traceback and the blamed file to find the root cause.", ember: true },
  fix_proposed: { text: "Waiting for a Docker sandbox to test the patch.", ember: false },
  validated: { text: "Passed validation. No pull request yet.", ember: false },
};

export function PendingLine({ status }: { status: IncidentStatus }) {
  const p = PENDING[status];
  if (!p) return null;
  return (
    <div className="flex items-center gap-2.5 rounded-box border border-line bg-surface px-4 py-3 text-[14px] text-body">
      <span
        aria-hidden
        className={cn("h-2 w-2 shrink-0 rounded-full", p.ember ? "bg-ember" : "border-[1.5px] border-muted")}
      />
      {p.text}
    </div>
  );
}
