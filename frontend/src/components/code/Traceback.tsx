import type { IncidentError } from "../../types/incident";
import { cn } from "../../lib/cn";
import { parseUnifiedDiff, type DiffLine } from "../../lib/diff";
import { py } from "./py";

// ---------------------------------------------------------------------------
// Static traceback and diff views. The animated variant lives in
// components/signature/HealingTraceback.tsx; this pair is what the dashboard
// uses once the sequence is over and you just need to read the thing.
// ---------------------------------------------------------------------------

export function TracebackView({ error, className }: { error: IncidentError; className?: string }) {
  return (
    <div className={cn("mono-pane overflow-x-auto rounded-md border border-ash-800 bg-ash-925 py-3", className)}>
      <div className="px-4 text-bone-3">Traceback (most recent call last):</div>
      {error.frames.map((frame, i) => (
        <div key={i} className={cn("px-4", frame.blame && "bg-sodium/6")}>
          <div className="whitespace-pre text-bone-3">
            {"  File "}
            <span className="text-[var(--color-code-lit)]">"{frame.file}"</span>
            {", line "}
            <span className="text-[var(--color-code-lit)]">{frame.line}</span>
            {", in "}
            <span className={frame.blame ? "text-sodium" : "text-bone"}>{frame.function}</span>
          </div>
          <div className="whitespace-pre">
            {"    "}
            {py(frame.code)}
          </div>
        </div>
      ))}
      <div className="whitespace-pre px-4 font-medium text-brick">
        {error.exception_type}
        <span className="text-bone-2">: {error.message}</span>
      </div>
    </div>
  );
}

/** Gutter number, sign and highlighting for each kind of diff line. */
const LINE_STYLE: Record<DiffLine["kind"], { row: string; tone: string; sign: string }> = {
  del: { row: "diff-del", tone: "text-brick", sign: "−" },
  add: { row: "diff-add", tone: "text-jade", sign: "+" },
  context: { row: "", tone: "text-bone-4", sign: " " },
};

export function DiffView({ diff }: { diff: string }) {
  const files = parseUnifiedDiff(diff);

  if (files.length === 0) {
    return (
      <pre className="mono-pane overflow-x-auto rounded-md border border-ash-800 bg-ash-925 px-4 py-3 text-bone-2">
        {diff}
      </pre>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-ash-800 bg-ash-925">
      {files.map((file, f) => (
        <div key={f} className={f > 0 ? "border-t border-ash-800" : undefined}>
          <div className="flex items-center gap-3 border-b border-ash-800 px-4 py-2">
            <span className="truncate font-mono text-[11.5px] text-bone-2">
              {file.newPath ?? file.oldPath}
            </span>
            {file.oldPath === null && <span className="ml-auto font-mono text-[10.5px] text-jade">new file</span>}
            {file.newPath === null && <span className="ml-auto font-mono text-[10.5px] text-brick">deleted</span>}
          </div>
          {file.hunks.map((hunk, h) => (
            <div key={h} className={h > 0 ? "border-t border-ash-800/60" : undefined}>
              <div className="truncate px-4 pt-2 font-mono text-[10.5px] tracking-[0.1em] text-bone-4">
                {hunk.header}
              </div>
              <div className="mono-pane overflow-x-auto py-1.5">
                {hunk.lines.map((line, i) => {
                  const style = LINE_STYLE[line.kind];
                  return (
                    <div key={i} className={cn("flex items-baseline", style.row)}>
                      <span aria-hidden className={cn("tnum w-12 shrink-0 pr-3 text-right text-[11px]", style.tone)}>
                        {line.kind === "del" ? line.oldLine : line.newLine}
                      </span>
                      <span aria-hidden className={cn("w-4 shrink-0", style.tone)}>
                        {style.sign}
                      </span>
                      {line.kind === "del" ? (
                        <code className="whitespace-pre pr-6 text-bone-2">{line.text}</code>
                      ) : (
                        <code className={cn("whitespace-pre pr-6", line.kind === "context" && "text-bone-3 opacity-70")}>
                          {py(line.text)}
                        </code>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
