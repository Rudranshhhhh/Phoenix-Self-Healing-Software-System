import type { IncidentStatus } from "../../types/incident";
import { ARC_STAGES, arcPosition } from "../phoenix/PipelineArc";
import { cn } from "../../lib/cn";

/** Six 8px dots: ink done, Ember current, red rejected, outlined future. */
export function MiniPipeline({ status, className }: { status: IncidentStatus; className?: string }) {
  const { index, rejected } = arcPosition(status);
  // PR opened is finished, not "Phoenix acting now": all six dots go ink.
  const finished = status === "pr_opened";
  return (
    <span aria-hidden className={cn("flex items-center gap-1", className)}>
      {ARC_STAGES.map((stage, i) => (
        <span
          key={stage.status}
          className={cn(
            "h-2 w-2 rounded-full",
            i < index || (finished && i === index)
              ? "bg-body"
              : i === index
                ? rejected
                  ? "bg-fail"
                  : "bg-ember"
                : "border-[1.5px] border-[#B7B0AA]",
          )}
        />
      ))}
    </span>
  );
}
