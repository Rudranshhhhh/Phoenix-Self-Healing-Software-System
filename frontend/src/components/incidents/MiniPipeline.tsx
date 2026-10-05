import type { IncidentStatus } from "../../types/incident";
import { ARC_STAGES, arcPosition } from "../phoenix/PipelineArc";
import { isActing } from "../../lib/incident";
import { cn } from "../../lib/cn";

/** Six 8px dots: ink done, Ember current while Phoenix acts, ink current while waiting, red rejected, outlined future. */
export function MiniPipeline({ status, className }: { status: IncidentStatus; className?: string }) {
  const { index, rejected } = arcPosition(status);
  const acting = isActing(status);
  return (
    <span aria-hidden className={cn("flex items-center gap-1", className)}>
      {ARC_STAGES.map((stage, i) => (
        <span
          key={stage.status}
          className={cn(
            "h-2 w-2 rounded-full",
            i < index || (i === index && !rejected && !acting)
              ? "bg-body"
              : i === index
                ? rejected
                  ? "bg-fail"
                  : "bg-ember"
                : "border-[1.5px] border-line-strong",
          )}
        />
      ))}
    </span>
  );
}
