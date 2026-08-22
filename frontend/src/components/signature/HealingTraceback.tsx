import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, GitPullRequest, RotateCcw } from "lucide-react";
import type { Incident } from "../../types/phoenix";
import { cn } from "../../lib/cn";
import { py } from "../code/py";
import { Chip, Dot, Label } from "../ui/Primitives";
import { usePrefersReducedMotion } from "../../hooks/useReveal";

// ============================================================================
// The signature element.
//
// A captured traceback reads itself, marks the frame it blames, and the guilty
// line splits into a real diff. It stops there and waits — opening the pull
// request is the visitor's click, because that is exactly how the product works.
//
// The same component backs the home page hero and the dashboard's fix panel.
// ============================================================================

/** 0 print · 1 read · 2 blame · 3 patch · 4 tests · 5 pull request open */
type Phase = 0 | 1 | 2 | 3 | 4 | 5;

const BEATS: Array<{ to: Phase; after: number }> = [
  { to: 1, after: 900 },
  { to: 2, after: 1150 },
  { to: 3, after: 1000 },
  { to: 4, after: 1250 },
];

const PHASE_NOTE: Record<Phase, string> = {
  0: "Receiving report",
  1: "Reading stack",
  2: "Frame blamed",
  3: "Patch written",
  4: "Tests passed",
  5: "Pull request open",
};

interface Props {
  incident: Incident;
  /** Skip the scripted sequence and render the finished state. */
  autoplay?: boolean;
  className?: string;
}

export function HealingTraceback({ incident, autoplay = true, className }: Props) {
  const reduced = usePrefersReducedMotion();
  const [phase, setPhase] = useState<Phase>(() => (autoplay && !reduced ? 0 : 4));
  const [printed, setPrinted] = useState(() => (autoplay && !reduced ? 0 : 99));
  const timers = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const [runId, setRunId] = useState(0);

  const fix = incident.fix;
  const hunk = fix?.hunks[0];
  const blameIndex = incident.frames.findIndex((f) => f.blame);

  const lines = useMemo(() => {
    const rows: Array<{ kind: "head" | "file" | "code" | "exc"; frame: number }> = [
      { kind: "head", frame: -1 },
    ];
    incident.frames.forEach((_, i) => {
      rows.push({ kind: "file", frame: i });
      rows.push({ kind: "code", frame: i });
    });
    rows.push({ kind: "exc", frame: -1 });
    return rows;
  }, [incident.frames]);

  const clear = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  // Print the traceback a line at a time, then walk the beats.
  useEffect(() => {
    if (!autoplay || reduced) return;
    clear();
    lines.forEach((_, i) => {
      timers.current.push(setTimeout(() => setPrinted(i + 1), 110 * (i + 1)));
    });
    let at = 110 * lines.length;
    for (const beat of BEATS) {
      at += beat.after;
      timers.current.push(setTimeout(() => setPhase(beat.to), at));
    }
    return clear;
  }, [autoplay, reduced, lines, clear, runId]);

  const replay = () => {
    clear();
    setPhase(0);
    setPrinted(0);
    setRunId((n) => n + 1);
  };

  const scanning = phase === 1;
  const patched = phase >= 3;
  const noteTone = phase >= 5 ? "healthy" : phase >= 3 ? "working" : "failing";

  return (
    <figure
      className={cn(
        "relative overflow-hidden rounded-lg border border-ash-700 bg-ash-900 shadow-[0_28px_70px_-40px_rgba(0,0,0,0.9)]",
        className,
      )}
    >
      {/* ---- header: what was captured -------------------------------- */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-ash-800 bg-ash-925 px-4 py-3 sm:px-5">
        <span className="flex items-center gap-2">
          <Dot tone={phase >= 5 ? "healthy" : "failing"} pulse={phase < 5} />
          <Label className="text-bone-2">{incident.id}</Label>
        </span>
        <span className="hidden h-3 w-px bg-ash-700 sm:block" />
        <span className="tnum text-[11.5px] text-bone-3">
          {incident.request.method} {incident.request.path}
          <span className="text-brick"> → {incident.request.status}</span>
          <span className="text-bone-4"> · {incident.count} events · {incident.usersAffected} users</span>
        </span>
        <span className="ml-auto flex items-center gap-2">
          <Dot tone={noteTone} pulse={phase > 0 && phase < 4} />
          <Label className={phase >= 4 ? "text-jade" : "text-sodium"}>{PHASE_NOTE[phase]}</Label>
        </span>
      </div>

      {/* ---- the traceback -------------------------------------------- */}
      <div className="relative">
        {scanning && (
          <div
            aria-hidden
            className="scanline pointer-events-none absolute inset-x-0 top-0 z-10 h-8 blur-[1px]"
            style={{ animation: "scanDown 1.05s cubic-bezier(0.4,0,0.2,1) both" }}
          />
        )}

        <div className="mono-pane py-3.5">
          {lines.map((row, i) => {
            const visible = i < printed;
            const frame = row.frame >= 0 ? incident.frames[row.frame] : null;
            const isBlame = row.frame === blameIndex;
            const marked = isBlame && phase >= 2;

            // The guilty source line is where the diff happens.
            if (row.kind === "code" && isBlame && patched && hunk) {
              return (
                <div key={i} className="mt-1">
                  {hunk.removed.map((text, k) => (
                    <div key={`d${k}`} className="diff-del flex items-baseline">
                      <span aria-hidden className="w-11 shrink-0 pr-3 text-right text-brick">
                        −
                      </span>
                      <code className="whitespace-pre pr-6 text-bone-2 line-through decoration-brick/50">
                        {text.trim()}
                      </code>
                    </div>
                  ))}
                  {/* 0fr → 1fr lets the added lines push the pane open. */}
                  <div
                    className="grid transition-[grid-template-rows] duration-500 ease-out"
                    style={{ gridTemplateRows: patched ? "1fr" : "0fr" }}
                  >
                    <div className="overflow-hidden">
                      {hunk.added.map((text, k) => (
                        <div key={`a${k}`} className="diff-add flex items-baseline">
                          <span aria-hidden className="w-11 shrink-0 pr-3 text-right text-jade">
                            +
                          </span>
                          <code className="whitespace-pre pr-6">{py(text.trim())}</code>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            }

            return (
              <div
                key={i}
                className={cn(
                  "flex items-baseline transition-[opacity,background-color] duration-300",
                  visible ? "opacity-100" : "opacity-0",
                  marked && "bg-sodium/6",
                )}
              >
                {/* gutter: carries the blame marker */}
                <span
                  aria-hidden
                  className={cn(
                    "w-11 shrink-0 pr-3 text-right text-[11px] transition-colors",
                    marked ? "text-sodium" : "text-transparent",
                  )}
                >
                  {marked ? "▸" : "·"}
                </span>

                {row.kind === "head" && (
                  <code className="text-bone-3">Traceback (most recent call last):</code>
                )}

                {row.kind === "file" && frame && (
                  <code className="whitespace-pre pr-6 text-bone-3">
                    {"  File "}
                    <span className="text-[var(--color-code-lit)]">"{frame.file}"</span>
                    {", line "}
                    <span className="text-[var(--color-code-lit)]">{frame.line}</span>
                    {", in "}
                    <span className={cn(marked ? "text-sodium" : "text-bone")}>{frame.fn}</span>
                  </code>
                )}

                {row.kind === "code" && frame && (
                  <code className="whitespace-pre pr-6">{"    "}{py(frame.code)}</code>
                )}

                {row.kind === "exc" && (
                  <code className="whitespace-pre pr-6 font-medium text-brick">
                    {incident.exception}
                    <span className="text-bone-2">: {incident.message}</span>
                  </code>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ---- footer: the hand-off to a human -------------------------- */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-3 border-t border-ash-800 bg-ash-925 px-4 py-3 sm:px-5">
        {phase < 3 && (
          <span className="font-mono text-[11.5px] text-bone-4">
            Phoenix has not changed anything yet.
          </span>
        )}

        {phase >= 3 && fix && (
          <>
            <Chip tone={phase >= 4 ? "jade" : "iris"}>
              {phase >= 4 ? `${fix.testsPassed}/${fix.testsRun} tests` : "running tests"}
            </Chip>
            <span className="truncate font-mono text-[11.5px] text-bone-3">{fix.branch}</span>
          </>
        )}

        <span className="ml-auto flex items-center gap-3">
          {phase >= 4 && phase < 5 && (
            <button
              type="button"
              onClick={() => setPhase(5)}
              className="group inline-flex h-9 items-center gap-2 rounded-sm border border-sodium bg-sodium px-3.5 text-[13px] font-semibold text-ash-950 transition-colors hover:bg-[#ffc648] hover:border-[#ffc648]"
            >
              Open pull request
              <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
            </button>
          )}
          {phase >= 5 && (
            <span className="inline-flex items-center gap-2 font-mono text-[11.5px] text-jade">
              <GitPullRequest size={13} />
              pull request #1204 opened · waiting on your review
            </span>
          )}
          {(phase >= 5 || reduced) && autoplay && (
            <button
              type="button"
              onClick={replay}
              className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-bone-4 transition-colors hover:text-bone-2"
            >
              <RotateCcw size={11} />
              Replay
            </button>
          )}
        </span>
      </div>

      <style>{`@keyframes scanDown { from { transform: translateY(0) } to { transform: translateY(var(--scan-end, 190px)) } }`}</style>
    </figure>
  );
}
