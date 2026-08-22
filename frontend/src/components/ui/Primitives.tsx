import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** Monospace eyebrow. Used above every section and on every data column. */
export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("ledger-label", className)}>{children}</span>;
}

/**
 * A section eyebrow with the hairline that runs off to the right — the ruled
 * line of the ledger. The label sits in the margin, the rule carries the eye.
 */
export function SectionRule({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <Label className="shrink-0 text-sodium/70">{children}</Label>
      <span className="h-px flex-1 bg-ash-800" />
    </div>
  );
}

type DotTone = "healthy" | "degraded" | "failing" | "offline" | "working";

const DOTS: Record<DotTone, string> = {
  healthy: "bg-jade",
  degraded: "bg-sodium",
  failing: "bg-brick",
  offline: "bg-bone-4",
  working: "bg-iris",
};

/** Status dot. Pulses only while something is actually moving. */
export function Dot({ tone, pulse = false }: { tone: DotTone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      {pulse && <span className={cn("absolute inset-0 rounded-full animate-breathe", DOTS[tone])} />}
      <span className={cn("relative m-auto h-1.5 w-1.5 rounded-full", DOTS[tone])} />
    </span>
  );
}

type ChipTone = "neutral" | "sodium" | "brick" | "jade" | "iris";

const CHIPS: Record<ChipTone, string> = {
  neutral: "border-ash-700 text-bone-2 bg-ash-850",
  sodium: "border-sodium/35 text-sodium bg-sodium/8",
  brick: "border-brick/35 text-brick bg-brick/8",
  jade: "border-jade/35 text-jade bg-jade/8",
  iris: "border-iris/35 text-iris bg-iris/8",
};

export function Chip({
  tone = "neutral",
  children,
  className,
}: {
  tone?: ChipTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-xs border px-2 py-[3px] font-mono text-[10.5px] font-medium uppercase tracking-[0.1em]",
        CHIPS[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
