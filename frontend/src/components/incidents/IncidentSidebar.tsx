import type { ReactNode } from "react";
import type { Incident, IncidentStatus, PullRequest } from "../../types/incident";
import { duration } from "../../lib/format";
import { statusLabel } from "../../lib/status";
import { blamedFrame, isActing, isActive } from "../../lib/incident";
import { Chip } from "./DetailSections";

const DOTS = 12;

type Tone = "done" | "now" | "wait" | "fail";

interface StageRow {
  status: IncidentStatus;
  secs: number;
  tone: Tone;
}

/** One row per stage the incident has been in, from the timeline. Rejected / PR opened are end states, not rows. */
function stageRows(incident: Incident, now: number): StageRow[] {
  const tl = incident.timeline;
  const rows: StageRow[] = [];
  for (let i = 0; i < tl.length; i++) {
    const entry = tl[i];
    if (entry.status === "rejected" || entry.status === "pr_opened") break;
    const start = new Date(entry.at).getTime();
    const next = tl[i + 1];
    if (next) {
      rows.push({
        status: entry.status,
        secs: Math.max(0, (new Date(next.at).getTime() - start) / 1000),
        tone: next.status === "rejected" ? "fail" : "done",
      });
    } else {
      rows.push({ status: entry.status, secs: Math.max(0, (now - start) / 1000), tone: isActing(entry.status) ? "now" : "wait" });
    }
  }
  return rows;
}

const DOT_ON: Record<Tone, string> = { done: "bg-body", now: "bg-ember", wait: "bg-body", fail: "bg-fail" };

/** Dots are relative to the longest stage of this incident (at least one dot). */
function DotBar({ secs, max, tone }: { secs: number; max: number; tone: Tone }) {
  const n = Math.max(1, Math.min(DOTS, Math.round((DOTS * secs) / max)));
  return (
    <span aria-hidden className="flex gap-[3px]">
      {Array.from({ length: DOTS }, (_, i) => (
        <span key={i} className={`size-[5px] rounded-full ${i < n ? DOT_ON[tone] : "bg-[#D6D0CA]"}`} />
      ))}
    </span>
  );
}

const PR_STATE: Record<PullRequest["state"], string> = {
  open: "Waiting for review",
  merged: "Merged",
  closed: "Closed",
};

function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-3.5 border-b border-line pb-3.5 last:mb-0 last:border-b-0 last:pb-0">
      <h3 className="mb-1.5 text-[12px] font-semibold text-muted">{title}</h3>
      {children}
    </div>
  );
}

const Sub = ({ children }: { children: ReactNode }) => (
  <p className="text-[13px] text-muted [overflow-wrap:anywhere]">{children}</p>
);

function runNumber(url: string | null): string | null {
  const m = url?.match(/\/runs\/(\d+)/);
  return m ? m[1] : null;
}

export function IncidentSidebar({ incident, branch, now }: { incident: Incident; branch: string; now: number }) {
  const rows = stageRows(incident, now);
  const max = Math.max(60, ...rows.map((r) => r.secs));
  const total = rows.reduce((sum, r) => sum + r.secs, 0);
  const { source, diagnosis, pull_request: pr } = incident;
  const blame = blamedFrame(incident.error);
  const file = diagnosis?.suspect_file ?? blame?.file ?? null;
  const line = diagnosis?.suspect_line ?? blame?.line ?? null;
  const run = runNumber(source.workflow_run_url);

  return (
    <aside aria-label="Incident details" className="min-w-0 grow basis-[260px] text-[14px] text-body">
      <Part title="Time in each stage">
        <ul>
          {rows.map((r) => (
            <li key={r.status} className="grid grid-cols-[88px_1fr_auto] items-center gap-2 py-[3px] text-[12px]">
              <span>{statusLabel(r.status)}</span>
              <DotBar secs={r.secs} max={max} tone={r.tone} />
              <span className="whitespace-nowrap font-mono tabular-nums text-muted">
                {duration(r.secs)}
                {r.tone === "now" || r.tone === "wait" ? " so far" : ""}
              </span>
            </li>
          ))}
          {incident.status === "pr_opened" && pr && (
            <li className="grid grid-cols-[88px_1fr_auto] items-center gap-2 py-[3px] text-[12px]">
              <span>{statusLabel("pr_opened")}</span>
              <span />
              <span className="whitespace-nowrap text-muted">{PR_STATE[pr.state]}</span>
            </li>
          )}
        </ul>
        <div className="mt-1.5 flex justify-between border-t border-dashed border-line pt-1.5 text-[12px] text-muted">
          <span>{isActive(incident.status) ? "Total so far" : "Total"}</span>
          <span className="font-mono tabular-nums">{duration(total)}</span>
        </div>
      </Part>

      <Part title="Source">
        {source.type === "github_actions" ? (
          <>
            <p className="[overflow-wrap:anywhere]">
              {source.workflow_run_url ? (
                <a
                  href={source.workflow_run_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ink underline underline-offset-[3px]"
                >
                  CI run{run ? ` #${run}` : ""}
                </a>
              ) : (
                "CI run"
              )}
            </p>
            <Sub>GitHub Actions on {branch}</Sub>
          </>
        ) : (
          <>
            <p className="font-mono text-[13px] [overflow-wrap:anywhere]">{source.container ?? "Unknown container"}</p>
            <Sub>Runtime error in a Docker container</Sub>
          </>
        )}
      </Part>

      {source.commit_sha && (
        <Part title="Commit">
          <p className="font-mono text-[13px]">{source.commit_sha.slice(0, 7)}</p>
        </Part>
      )}

      <Part title="Blamed file">
        {file ? (
          <p className="font-mono text-[13px] [overflow-wrap:anywhere]">
            {file}
            {line != null ? `, line ${line}` : ""}
          </p>
        ) : (
          <Sub>Known once Phoenix finds the root cause.</Sub>
        )}
      </Part>

      <Part title="Fix branch">
        {pr ? (
          <Chip>{pr.branch}</Chip>
        ) : incident.status === "rejected" ? (
          <Sub>None. The fix didn't pass validation.</Sub>
        ) : (
          <Sub>Created with the pull request.</Sub>
        )}
      </Part>
    </aside>
  );
}
