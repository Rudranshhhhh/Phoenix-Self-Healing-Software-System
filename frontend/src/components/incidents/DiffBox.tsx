import type { DiffFile, DiffLine } from "../../lib/diff";
import { cn } from "../../lib/cn";

export function diffCounts(files: DiffFile[]): { add: number; del: number } {
  let add = 0;
  let del = 0;
  for (const file of files)
    for (const hunk of file.hunks)
      for (const line of hunk.lines) {
        if (line.kind === "add") add += 1;
        else if (line.kind === "del") del += 1;
      }
  return { add, del };
}

const ROW: Record<DiffLine["kind"], string> = { context: "", add: "bg-add-bg", del: "bg-del-bg" };
const SIGN: Record<DiffLine["kind"], string> = { context: " ", add: "+", del: "−" };
const SIGN_TONE: Record<DiffLine["kind"], string> = {
  context: "text-muted",
  add: "font-semibold text-pass",
  del: "font-semibold text-fail",
};
const SR: Record<DiffLine["kind"], string> = { context: "", add: "Added: ", del: "Removed: " };
const GUTTER = "w-11 shrink-0 select-none pr-2 text-right text-muted";

/** Light unified diff: old/new line numbers, sign, text. Falls back to the raw diff. */
export function DiffBox({ files, raw }: { files: DiffFile[]; raw: string }) {
  if (files.length === 0) {
    return (
      <pre className="overflow-x-auto bg-code px-4 py-2 font-mono text-[12px] leading-5 text-body">{raw}</pre>
    );
  }
  return (
    <div className="overflow-x-auto bg-code font-mono text-[12px] leading-5 text-body">
      <div className="inline-block min-w-full">
        {files.map((file, f) => (
          <div key={f} className={f > 0 ? "border-t border-line" : undefined}>
            {files.length > 1 && (
              <div className="whitespace-pre border-b border-line bg-surface px-4 py-1.5 font-semibold text-ink">
                {file.newPath ?? file.oldPath}
                {file.oldPath === null ? "  (new file)" : file.newPath === null ? "  (deleted)" : ""}
              </div>
            )}
            {file.hunks.map((hunk, h) => (
              <div key={h}>
                <div className="whitespace-pre bg-subtle px-4 text-muted">{hunk.header}</div>
                {hunk.lines.map((line, i) => (
                  <div key={i} className={cn("flex whitespace-pre", ROW[line.kind])}>
                    <span aria-hidden className={GUTTER}>{line.oldLine ?? ""}</span>
                    <span aria-hidden className={GUTTER}>{line.newLine ?? ""}</span>
                    <span aria-hidden className={cn("w-5 shrink-0 select-none text-center", SIGN_TONE[line.kind])}>
                      {SIGN[line.kind]}
                    </span>
                    <span className="pr-4">
                      <span className="sr-only">{SR[line.kind]}</span>
                      {line.text}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
