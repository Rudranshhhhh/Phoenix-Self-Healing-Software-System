import type { IncidentStatus } from "../../types/incident";
import { statusLabel } from "../../lib/status";
import { cn } from "../../lib/cn";
import { StatusIcon } from "./StatusIcon";

const TEXT: Record<IncidentStatus, string> = {
  detected: "text-body",
  diagnosing: "text-body",
  fix_proposed: "text-body",
  validating: "text-body",
  validated: "text-pass",
  pr_opened: "text-pass",
  rejected: "text-fail",
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-box border border-line bg-surface px-2.5 py-1 text-[13px] font-semibold",
        TEXT[status],
      )}
    >
      <StatusIcon status={status} />
      {statusLabel(status)}
    </span>
  );
}
