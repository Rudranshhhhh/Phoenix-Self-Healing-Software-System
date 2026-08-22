import { useEffect, useRef } from "react";
import { Undo2 } from "lucide-react";
import type { FeedEntry } from "../../types/phoenix";
import type { FaultKind } from "../../mock/engine";
import { FAULTS } from "../../mock/engine";
import { clock } from "../../lib/format";
import { cn } from "../../lib/cn";
import { Label } from "../ui/Primitives";

// ---------------------------------------------------------------------------
// Live feed
// ---------------------------------------------------------------------------

const KIND_STYLE: Record<FeedEntry["kind"], string> = {
  info: "text-bone-2",
  warn: "text-sodium",
  error: "text-brick",
  repair: "text-jade",
};

const KIND_GLYPH: Record<FeedEntry["kind"], string> = {
  info: "·",
  warn: "!",
  error: "×",
  repair: "+",
};

export function EventFeed({ entries }: { entries: FeedEntry[] }) {
  const scroller = useRef<HTMLDivElement | null>(null);
  const pinned = useRef(true);

  // Stay pinned to the newest line unless the reader has scrolled up.
  useEffect(() => {
    const node = scroller.current;
    if (node && pinned.current) node.scrollTop = node.scrollHeight;
  }, [entries]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-ash-800 bg-ash-900">
      <div className="flex items-center gap-3 border-b border-ash-800 bg-ash-925 px-4 py-2.5">
        <Label>Reporter feed</Label>
        <span className="ml-auto font-mono text-[10.5px] text-bone-4">{entries.length} lines</span>
      </div>

      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
        }}
        className="mono-pane min-h-0 flex-1 overflow-y-auto px-4 py-3"
      >
        {entries.map((entry) => (
          <div key={entry.id} className="flex gap-2.5 py-[1px]">
            <span className="tnum shrink-0 text-[11px] text-bone-4">{clock(entry.t)}</span>
            <span aria-hidden className={cn("w-2 shrink-0 text-center", KIND_STYLE[entry.kind])}>
              {KIND_GLYPH[entry.kind]}
            </span>
            <span className="shrink-0 text-[11.5px] text-bone-4">{entry.source}</span>
            <span className={cn("min-w-0 text-[11.5px]", KIND_STYLE[entry.kind])}>{entry.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Walkthrough controls
// ---------------------------------------------------------------------------

export function FailurePanel({
  active,
  onInject,
  onClear,
}: {
  active: FaultKind[];
  onInject: (kind: FaultKind) => void;
  onClear: () => void;
}) {
  return (
    <section className="rounded-lg border border-ash-800 bg-ash-925 p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Label className="text-bone-3">Walkthrough controls</Label>
        <p className="text-[13.5px] text-bone-3">
          Break the sample process on purpose, then watch the strip, the feed and the incident list react.
        </p>
        {active.length > 0 && (
          <button
            onClick={onClear}
            className="ml-auto inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-bone-3 transition-colors hover:text-bone"
          >
            <Undo2 size={12} />
            Restore baseline
          </button>
        )}
      </div>

      <div className="mt-5 grid gap-px overflow-hidden rounded-md border border-ash-800 bg-ash-800 sm:grid-cols-2 lg:grid-cols-4">
        {FAULTS.map((fault) => {
          const on = active.includes(fault.kind);
          return (
            <button
              key={fault.kind}
              type="button"
              onClick={() => onInject(fault.kind)}
              disabled={on}
              className={cn(
                "px-4 py-3.5 text-left transition-colors",
                on ? "bg-brick/10" : "bg-ash-900 hover:bg-ash-850",
              )}
            >
              <span className="flex items-center gap-2">
                <span className={cn("font-mono text-[12.5px]", on ? "text-brick" : "text-bone")}>
                  {fault.label}
                </span>
                {on && (
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-brick">live</span>
                )}
              </span>
              <span className="mt-1 block text-[12px] leading-snug text-bone-4">{fault.hint}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
