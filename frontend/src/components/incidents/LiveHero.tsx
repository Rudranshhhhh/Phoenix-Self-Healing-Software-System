import { Link } from "react-router-dom";
import type { Incident, IncidentStatus, IncidentSummary } from "../../types/incident";
import { PipelineArc } from "../phoenix/PipelineArc";
import { blamedFile, isActive, stageClock, stageStartMs } from "../../lib/incident";
import { useNow } from "../../hooks/useNow";

const VERB: Record<IncidentStatus, string> = {
  detected: "Picked up",
  diagnosing: "Diagnosing",
  fix_proposed: "Fix written for",
  validating: "Testing the fix for",
  validated: "Fix passed for",
  pr_opened: "Pull request opened for",
  rejected: "Fix rejected for",
};

function subline(summary: IncidentSummary, incident: Incident | null, branch: string): string {
  switch (summary.status) {
    case "detected":
      return summary.source_type === "github_actions"
        ? `A CI run failed on ${branch}.`
        : "A running container threw an exception.";
    case "diagnosing": {
      const file = blamedFile(incident);
      return file ? `Reading the traceback and ${file}.` : "Reading the traceback.";
    }
    case "fix_proposed": {
      const files = incident?.patch?.files_changed ?? [];
      return files.length > 0
        ? `${files.length} ${files.length === 1 ? "file" : "files"} changed: ${files.join(", ")}.`
        : "Writing the smallest change that stops it.";
    }
    case "validating":
      return "Running the tests in a Docker sandbox.";
    case "validated": {
      const v = incident?.validation;
      return v ? `${v.tests_passed} of ${v.tests_run} tests passed.` : "The fix passed validation.";
    }
    case "pr_opened": {
      const pr = incident?.pull_request;
      return pr ? `Pull request #${pr.number} is waiting for review.` : "The pull request is waiting for review.";
    }
    case "rejected":
      return "The fix failed validation, so no pull request was opened.";
  }
}

export function LiveHero({
  summary,
  incident,
  branch,
}: {
  summary: IncidentSummary | null;
  incident: Incident | null;
  branch: string;
}) {
  const active = summary !== null && isActive(summary.status);
  const now = useNow(active);

  if (!summary) {
    return (
      <section aria-label="Pipeline" className="mb-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-1">
          <h2 className="text-[20px] font-semibold leading-[1.3] text-ink">No incidents.</h2>
          <p className="text-[14px] text-muted">Phoenix is watching {branch}.</p>
        </div>
        <PipelineArc status={null} />
      </section>
    );
  }

  const clock = active ? stageClock(now - stageStartMs(summary.status, incident?.timeline, summary.updated_at)) : undefined;
  const file = blamedFile(incident);

  return (
    <section aria-label="Live incident" className="mb-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-1">
        <h2 className="text-[20px] font-semibold leading-[1.3] text-ink">
          {VERB[summary.status]} <span className="font-dot text-[22px] font-bold">{summary.id}</span>
        </h2>
        <p className="text-[14px] text-muted">{subline(summary, incident, branch)}</p>
      </div>

      <PipelineArc status={summary.status} incidentId={summary.id} detail={clock} />

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-t border-line pb-1 pt-3.5">
        <span className="min-w-0 text-[14px] text-body [overflow-wrap:anywhere]">
          <span className="font-semibold text-ink">{summary.exception_type}:</span> {summary.message}
          {file && (
            <>
              {" "}in <span className="font-mono text-[13px]">{file}</span>
            </>
          )}
        </span>
        <Link
          to={`/app/incidents/${summary.id}`}
          className="inline-flex min-h-[44px] items-center rounded-box border border-ink bg-ink px-3 text-[13px] font-medium text-[#fff] no-underline hover:bg-body sm:min-h-8"
        >
          Open incident
        </Link>
      </div>
    </section>
  );
}
