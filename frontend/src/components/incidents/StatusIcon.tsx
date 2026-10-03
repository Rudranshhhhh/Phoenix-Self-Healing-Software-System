import type { IncidentStatus } from "../../types/incident";
import { cn } from "../../lib/cn";

type Kind = "detected" | "working" | "pass" | "pr" | "rejected";

function kindOf(status: IncidentStatus): Kind {
  switch (status) {
    case "detected":
      return "detected";
    case "diagnosing":
    case "fix_proposed":
    case "validating":
      return "working";
    case "validated":
      return "pass";
    case "pr_opened":
      return "pr";
    case "rejected":
      return "rejected";
  }
}

const COLOR: Record<Kind, string> = {
  detected: "text-body",
  working: "text-ember", // Phoenix is acting on it right now
  pass: "text-pass",
  pr: "text-pass",
  rejected: "text-fail",
};

/** 16px GitHub-issues-style status icon. Colour comes from currentColor. */
export function StatusIcon({ status, className }: { status: IncidentStatus; className?: string }) {
  const kind = kindOf(status);
  return (
    <span aria-hidden className={cn("inline-flex h-4 w-4 shrink-0", COLOR[kind], className)}>
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {kind === "pr" ? (
          <>
            <circle cx="4" cy="3.5" r="1.6" />
            <circle cx="4" cy="12.5" r="1.6" />
            <circle cx="12" cy="12.5" r="1.6" />
            <path d="M4 5.1v5.8M12 10.9V7a2 2 0 0 0-2-2H7.5M9 3.4L7.4 5 9 6.6" />
          </>
        ) : (
          <circle cx="8" cy="8" r="6.5" />
        )}
        {kind === "detected" && <circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none" />}
        {kind === "working" && <path d="M8 3.5a4.5 4.5 0 0 1 0 9z" fill="currentColor" stroke="none" />}
        {kind === "pass" && <path d="M5 8.2l2 2 4-4.2" />}
        {kind === "rejected" && <path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" />}
      </svg>
    </span>
  );
}
