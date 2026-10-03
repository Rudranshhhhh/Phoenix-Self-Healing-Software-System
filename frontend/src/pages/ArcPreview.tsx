import { useEffect, useState } from "react";
import { cn } from "../lib/cn";
import { ARC_STAGES, PipelineArc, type ArcStatus } from "../components/phoenix/PipelineArc";

const OPTIONS: { status: ArcStatus | null; label: string }[] = [
  ...ARC_STAGES.map((s) => ({ status: s.status, label: s.label })),
  { status: "rejected", label: "Rejected" },
  { status: null, label: "Empty" },
];

const NO_TIMER: (ArcStatus | null)[] = ["rejected", "pr_opened", null];

function next(status: ArcStatus | null): ArcStatus {
  const i = ARC_STAGES.findIndex((s) => s.status === status);
  return i < 0 ? "detected" : ARC_STAGES[(i + 1) % ARC_STAGES.length].status;
}

function elapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// cn only joins classes, so idle and active colours must never be applied together.
const button = (on: boolean) =>
  cn("h-8 rounded-box border px-3 text-sm", on ? "border-ink bg-ink text-white" : "border-line bg-surface");

/** Dev-only playground for the pipeline arc, at /dev/arc. */
export default function ArcPreview() {
  const [status, setStatus] = useState<ArcStatus | null>("detected");
  const [auto, setAuto] = useState(true);
  const [flat, setFlat] = useState(false);
  const [changedAt, setChangedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  const go = (s: ArcStatus | null) => {
    setStatus(s);
    setChangedAt(Date.now());
    setNow(Date.now());
  };

  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(() => {
      setStatus((s) => next(s));
      setChangedAt(Date.now());
      setNow(Date.now());
    }, 4000);
    return () => window.clearInterval(id);
  }, [auto]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const detail = NO_TIMER.includes(status) ? undefined : elapsed(now - changedAt);

  return (
    <div className="min-h-screen bg-page">
      <div className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6">
        <h1 className="mb-4 text-2xl font-semibold text-ink">Pipeline arc</h1>

        <div className="flex flex-wrap gap-2">
          {OPTIONS.map((o) => (
            <button
              key={o.label}
              type="button"
              aria-pressed={status === o.status}
              onClick={() => go(o.status)}
              className={button(status === o.status)}
            >
              {o.label}
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" aria-pressed={auto} onClick={() => setAuto((v) => !v)} className={button(auto)}>
            Auto-advance
          </button>
          <button type="button" aria-pressed={flat} onClick={() => setFlat((v) => !v)} className={button(flat)}>
            Flat character
          </button>
        </div>

        <div className="mt-8 border-b border-line">
          <PipelineArc status={status} incidentId="INC-008" detail={detail} variant={flat ? "flat" : "soft"} />
        </div>
      </div>
    </div>
  );
}
