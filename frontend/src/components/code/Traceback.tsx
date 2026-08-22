import type { Incident, PatchHunk } from "../../types/phoenix";
import { cn } from "../../lib/cn";
import { py } from "./py";

// ---------------------------------------------------------------------------
// Static traceback and diff views. The animated variant lives in
// components/signature/HealingTraceback.tsx; this pair is what the dashboard
// uses once the sequence is over and you just need to read the thing.
// ---------------------------------------------------------------------------

export function TracebackView({ incident, className }: { incident: Incident; className?: string }) {
  return (
    <div className={cn("mono-pane overflow-x-auto rounded-md border border-ash-800 bg-ash-925 py-3", className)}>
      <div className="px-4 text-bone-3">Traceback (most recent call last):</div>
      {incident.frames.map((frame, i) => (
        <div key={i} className={cn("px-4", frame.blame && "bg-sodium/6")}>
          <div className="whitespace-pre text-bone-3">
            {"  File "}
            <span className="text-[var(--color-code-lit)]">"{frame.file}"</span>
            {", line "}
            <span className="text-[var(--color-code-lit)]">{frame.line}</span>
            {", in "}
            <span className={frame.blame ? "text-sodium" : "text-bone"}>{frame.fn}</span>
          </div>
          <div className="whitespace-pre">
            {"    "}
            {py(frame.code)}
          </div>
        </div>
      ))}
      <div className="whitespace-pre px-4 font-medium text-brick">
        {incident.exception}
        <span className="text-bone-2">: {incident.message}</span>
      </div>
    </div>
  );
}

export function DiffView({ hunks }: { hunks: PatchHunk[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-ash-800 bg-ash-925">
      {hunks.map((hunk, h) => (
        <div key={h} className={h > 0 ? "border-t border-ash-800" : undefined}>
          <div className="flex items-center gap-3 border-b border-ash-800 px-4 py-2">
            <span className="truncate font-mono text-[11.5px] text-bone-2">{hunk.file}</span>
            <span className="ml-auto font-mono text-[10.5px] tracking-[0.1em] text-bone-4">
              @@ −{hunk.startLine},{hunk.removed.length} +{hunk.startLine},{hunk.added.length} @@
            </span>
          </div>
          <div className="mono-pane overflow-x-auto py-1.5">
            {hunk.removed.map((line, i) => (
              <div key={`d${i}`} className="diff-del flex items-baseline">
                <span aria-hidden className="tnum w-12 shrink-0 pr-3 text-right text-[11px] text-brick">
                  {hunk.startLine + i}
                </span>
                <span aria-hidden className="w-4 shrink-0 text-brick">
                  −
                </span>
                <code className="whitespace-pre pr-6 text-bone-2">{line}</code>
              </div>
            ))}
            {hunk.added.map((line, i) => (
              <div key={`a${i}`} className="diff-add flex items-baseline">
                <span aria-hidden className="tnum w-12 shrink-0 pr-3 text-right text-[11px] text-jade">
                  {hunk.startLine + i}
                </span>
                <span aria-hidden className="w-4 shrink-0 text-jade">
                  +
                </span>
                <code className="whitespace-pre pr-6">{py(line)}</code>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
