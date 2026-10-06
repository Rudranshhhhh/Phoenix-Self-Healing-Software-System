import { useMemo } from "react";
import { cn } from "../../lib/cn";
import { REPO } from "../../lib/repo";
import { isActing } from "../../lib/incident";
import { PhoenixChick, type ChickMood } from "./PhoenixChick";

export const ARC_STAGES = [
  { status: "detected", label: "Detected" },
  { status: "diagnosing", label: "Diagnosing" },
  { status: "fix_proposed", label: "Fix proposed" },
  { status: "validating", label: "Validating" },
  { status: "validated", label: "Validated" },
  { status: "pr_opened", label: "PR opened" },
] as const;

export type ArcStatus = (typeof ARC_STAGES)[number]["status"] | "rejected";

const MOODS: ChickMood[] = ["alert", "dizzy", "thinking", "focused", "smile", "happy"];
const OPACITY = [1, 0.85, 0.55, 0.3, 0.14, 0.07];

export function arcPosition(status: ArcStatus) {
  if (status === "rejected") return { index: 3, rejected: true };
  return { index: ARC_STAGES.findIndex((s) => s.status === status), rejected: false };
}

const SAY: Record<ArcStatus, string> = {
  detected: "A test just failed. Grabbing the traceback.",
  diagnosing: "Reading the code around the error.",
  fix_proposed: "Writing the smallest fix I can.",
  validating: "Running your tests on the patch.",
  validated: "Tests pass. The fix is on its own branch.",
  pr_opened: "PR is open. Your turn to review.",
  rejected: "Tests failed, so I left your code alone.",
};

const spin = (k: number) => `rotate(calc(var(--arc-step) * ${k}))`;

type Props = {
  /** null = nothing broken: empty dial with the sleeping chick */
  status: ArcStatus | null;
  /** shown huge and faint behind the dial */
  incidentId?: string;
  /** appended after "Step n of 6", e.g. an elapsed timer "0:12" */
  detail?: string;
  variant?: "soft" | "flat";
  className?: string;
  /** corner label; defaults to the demo repo in lib/repo.ts */
  repo?: { name: string; branch: string };
  /** speech bubble next to the chick (Home live card only) */
  say?: boolean;
};

export function PipelineArc({ status, incidentId, detail, variant = "soft", className, repo = REPO, say = false }: Props) {
  const empty = status === null;
  const { index, rejected } = empty ? { index: 0, rejected: false } : arcPosition(status);
  const parity = index % 2 === 0 ? "a" : "b";
  const acting = status !== null && isActing(status);
  const line = status ? SAY[status] : "Waiting for a build to break.";

  const ticks = useMemo(() => {
    const out: { k: number; op: number; done: boolean }[] = [];
    for (let m = -36; m <= 72; m++) {
      const k = m / 6;
      if (!empty && m % 6 === 0 && m >= 0 && m <= 30) continue;
      let op = Math.max(0, 1 - Math.abs(k - index) * 0.26);
      if (rejected && k > index) op = 0;
      if (!empty && (k < 0 || k > 5)) op *= 0.5;
      out.push({ k, op, done: !empty && k < index });
    }
    return out;
  }, [index, rejected, empty]);

  const fineTicks = useMemo(() => {
    const out: { k: number; op: number }[] = [];
    for (let m = -72; m <= 144; m++) {
      const k = m / 12;
      out.push({ k, op: Math.max(0, 0.9 - Math.abs(k - index) * 0.22) });
    }
    return out;
  }, [index]);

  const mood: ChickMood = empty ? "asleep" : rejected ? "neutral" : MOODS[index];
  const label = empty ? "" : rejected ? "Rejected" : ARC_STAGES[index].label;
  const step = rejected
    ? "Stopped at step 4 of 6"
    : `Step ${index + 1} of 6${detail ? `, ${detail}` : ""}`;

  return (
    <div
      role="group"
      aria-label={empty ? "Nothing to fix" : `Pipeline stage: ${label}`}
      className={cn("phx-arc", className)}
    >
      {incidentId && !empty && (
        <span aria-hidden="true" className="phx-arc-ghost font-dot">{incidentId}</span>
      )}
      {["x1", "x2", "x3", "x4"].map((x) => (
        <span key={x} aria-hidden="true" className={`phx-arc-cross ${x}`} />
      ))}
      <span aria-hidden="true" className="phx-arc-coord c1">{repo.name} / {repo.branch}</span>
      <span aria-hidden="true" className="phx-arc-coord c2">
        {empty ? "idle" : rejected ? "stopped" : `stage ${index + 1} / 6`}
      </span>
      <span aria-hidden="true" className="phx-arc-needle" />

      <div aria-hidden="true" className={cn("phx-arc-wbox", !empty && `w${parity}`)}>
        <div className="phx-arc-wheel" style={{ transform: spin(-index) }}>
          <span className="phx-arc-ring r0" />
          <span className="phx-arc-ring r1" />
          <span className="phx-arc-ring r2" />
          <span className="phx-arc-ring r3" />
          {fineTicks.map((t) => (
            <div key={`f${t.k}`} className="phx-arc-spoke" style={{ opacity: t.op, transform: spin(t.k) }}>
              <span className="phx-arc-tick2" />
            </div>
          ))}
          {ticks.map((t) => (
            <div key={`t${t.k}`} className={cn("phx-arc-spoke", t.done && "is-done")}
                 style={{ opacity: t.op, transform: spin(t.k) }}>
              <span className="phx-arc-tick" />
            </div>
          ))}
          {!empty && ARC_STAGES.map((s, i) => {
            const state = i < index ? "is-past" : i === index ? (rejected ? "is-rejected" : acting ? "is-current" : "is-current is-idle") : "is-future";
            const op = rejected && i > index ? 0 : OPACITY[Math.abs(i - index)];
            return (
              <div key={s.status} className={cn("phx-arc-spoke", state)} style={{ opacity: op, transform: spin(i) }}>
                <span className="phx-arc-num">{`0${i + 1}`}</span>
                <span className="phx-arc-dot" />
                <span className="phx-arc-name">{s.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {empty && <span aria-hidden="true" className="phx-arc-fdot" />}
      <div className={cn("phx-arc-char", `phx-fade-${parity}`)}>
        <span className="relative isolate inline-block">
          <span aria-hidden className="phx-halo" data-acting={acting ? "true" : "false"} />
          <PhoenixChick key={mood} mood={mood} variant={variant} />
          {say && (
            <span
              key={status ?? "idle"}
              role="status"
              className="phx-say absolute left-[calc(100%+12px)] top-2 hidden w-max max-w-[210px] rounded-box border border-line bg-code px-3 py-2 text-left text-[13px] leading-[1.45] text-body sm:block"
            >
              <span
                aria-hidden
                className="absolute -left-[6px] top-3 h-2.5 w-2.5 rotate-45 border-b border-l border-line bg-code"
              />
              {line}
            </span>
          )}
        </span>
      </div>
      {!empty && (
        <>
          <div aria-live="polite" className={cn("phx-arc-label font-dot", `phx-fade-${parity}`, rejected && "is-rejected-label")}>
            {label}
          </div>
          <div className="phx-arc-step">{step}</div>
        </>
      )}
    </div>
  );
}
