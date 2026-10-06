type Event = { status: string; at: string; message?: string | null };

const LABEL: Record<string, string> = {
  detected: "Detected",
  diagnosing: "Diagnosing",
  fix_proposed: "Fix proposed",
  validating: "Validating",
  validated: "Validated",
  rejected: "Rejected",
  pr_opened: "PR opened",
};
const ACTING = new Set(["diagnosing", "fix_proposed", "validating"]);

function fmtTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtGap(ms: number) {
  if (!Number.isFinite(ms) || ms < 0) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

function dotClass(status: string, isLast: boolean, current: string) {
  if (isLast && ACTING.has(current)) return "bg-ember";
  if (status === "rejected") return "bg-fail";
  if (status === "validated" || status === "pr_opened") return "bg-pass";
  return "bg-ink";
}

export function StatusTimeline({ events, current }: { events: Event[]; current: string }) {
  if (events.length === 0) return null;
  const first = new Date(events[0].at).getTime();
  const last = events[events.length - 1];
  const total = fmtGap(new Date(last.at).getTime() - first);

  return (
    <div>
      <ol>
        {events.map((e, i) => {
          const isLast = i === events.length - 1;
          const gap = i === 0 ? "" : fmtGap(new Date(e.at).getTime() - new Date(events[i - 1].at).getTime());
          return (
            <li key={`${e.status}-${i}`} className="relative pb-5 pl-7 last:pb-0">
              {!isLast && <span aria-hidden className="absolute bottom-0 left-[5px] top-4 w-px bg-line" />}
              <span
                aria-hidden
                className={`absolute left-0 top-[5px] h-[11px] w-[11px] rounded-full ${dotClass(e.status, isLast, current)}`}
              />
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span className="text-[14px] font-medium text-ink">{LABEL[e.status] ?? e.status}</span>
                <span className="font-mono text-[12px] text-muted">{fmtTime(e.at)}</span>
                {gap && <span className="font-mono text-[12px] text-muted">+{gap}</span>}
              </div>
              {e.message && <p className="mt-1 text-[14px] leading-[1.55] text-body">{e.message}</p>}
            </li>
          );
        })}
      </ol>
      {events.length > 1 && total && (
        <p className="mt-5 border-t border-line pt-3 font-mono text-[12px] text-muted">
          {total} from first signal to {(LABEL[last.status] ?? last.status).toLowerCase()}
        </p>
      )}
    </div>
  );
}
