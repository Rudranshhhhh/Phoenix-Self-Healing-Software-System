import { INCIDENT_STATUSES } from "../../types/incident";
import type { IncidentStatus } from "../../types/incident";
import { cn } from "../../lib/cn";

// ---------------------------------------------------------------------------
// The pipeline tracker above an expanded incident.
// ---------------------------------------------------------------------------

type StepState = "done" | "current" | "pending" | "failed";

/** `reached` is the earliest status at which the step counts as underway. */
const STEPS: Array<{ reached: IncidentStatus; label: string; detail: string }> = [
  { reached: "detected", label: "Detected", detail: "the reporter caught the exception" },
  { reached: "diagnosing", label: "Diagnosed", detail: "trace the failure to a root cause" },
  { reached: "fix_proposed", label: "Fix proposed", detail: "write the smallest change that stops it" },
  { reached: "validating", label: "Validated", detail: "reproduce, patch, run the suite in a sandbox" },
  { reached: "pr_opened", label: "PR opened", detail: "hand it to you for review" },
];

const order = (status: IncidentStatus) => INCIDENT_STATUSES.indexOf(status);

function stateOf(status: IncidentStatus, index: number): StepState {
  if (status === "rejected") {
    // Validation failed: everything before it is done, nothing after it happens.
    const validated = STEPS.findIndex((s) => s.reached === "validating");
    return index < validated ? "done" : index === validated ? "failed" : "pending";
  }
  // The last step has nothing after it to wait on: reaching it finishes it.
  if (status === "pr_opened") return "done";

  const at = order(status);
  const start = order(STEPS[index].reached);
  const next = index + 1 < STEPS.length ? order(STEPS[index + 1].reached) : Infinity;
  if (at >= next) return "done";
  if (at >= start) return "current";
  return "pending";
}

const BOX: Record<StepState, string> = {
  done: "border-jade/50 bg-jade/12 text-jade",
  current: "border-iris/60 bg-iris/12 text-iris",
  pending: "border-ash-700 text-bone-4",
  failed: "border-brick/60 bg-brick/12 text-brick",
};

const TEXT: Record<StepState, string> = {
  done: "text-jade",
  current: "text-iris",
  pending: "text-bone-4",
  failed: "text-brick",
};

export function Steps({ status }: { status: IncidentStatus }) {
  return (
    <ol className="grid gap-px overflow-hidden rounded-md border border-ash-800 bg-ash-800 sm:grid-cols-5">
      {STEPS.map((step, i) => {
        const state = stateOf(status, i);
        return (
          <li key={step.label} className="bg-ash-900 px-4 py-3">
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className={cn(
                  "grid h-4 w-4 shrink-0 place-items-center rounded-xs border font-mono text-[9px]",
                  BOX[state],
                )}
              >
                {state === "done" ? "✓" : state === "failed" ? "✕" : i + 1}
              </span>
              <span className={cn("font-mono text-[12px]", TEXT[state])}>
                {state === "failed" ? "Rejected" : step.label}
              </span>
              {state === "current" && <span className="animate-caret text-iris">▌</span>}
            </span>
            <span className="mt-1.5 block text-[11.5px] leading-snug text-bone-4">
              {state === "failed" ? "the patch did not pass validation" : step.detail}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
