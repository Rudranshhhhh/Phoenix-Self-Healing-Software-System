import type { ServiceProcess } from "../../types/phoenix";
import { duration } from "../../lib/format";
import { cn } from "../../lib/cn";
import { Sparkline } from "../charts/Chart";
import { Dot, Label } from "../ui/Primitives";

const STATUS_WORD: Record<ServiceProcess["status"], string> = {
  healthy: "healthy",
  degraded: "degraded",
  failing: "failing",
  offline: "offline",
};

/** A thin percentage bar. Reads as a ruled measure, not a progress bar. */
function Measure({ value, warn }: { value: number; warn: number }) {
  const colour = value >= warn * 1.2 ? "bg-brick" : value >= warn ? "bg-sodium" : "bg-bone-3";
  return (
    <span className="flex items-center gap-2">
      <span className="tnum w-11 text-right text-[12px] text-bone-2">{value.toFixed(0)}%</span>
      <span className="relative h-[3px] w-full min-w-8 max-w-24 overflow-hidden rounded-xs bg-ash-800">
        <span
          className={cn("absolute inset-y-0 left-0 transition-[width] duration-500 ease-out", colour)}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </span>
    </span>
  );
}

export function ProcessTable({
  processes,
  selected,
  onSelect,
}: {
  processes: ServiceProcess[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-ash-800">
      <div className="hidden grid-cols-[minmax(0,1fr)_7rem_9rem_9rem_5.5rem] items-center gap-4 border-b border-ash-800 bg-ash-925 px-4 py-2.5 md:grid">
        <Label>Process</Label>
        <Label>State</Label>
        <Label>CPU</Label>
        <Label>Memory</Label>
        <Label>Uptime</Label>
      </div>

      <ul className="divide-y divide-ash-800">
        {processes.map((p) => {
          const latest = p.history[p.history.length - 1];
          const active = p.id === selected;
          return (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => onSelect(p.id)}
                aria-pressed={active}
                className={cn(
                  "grid w-full grid-cols-2 items-center gap-x-4 gap-y-3 px-4 py-3.5 text-left transition-colors md:grid-cols-[minmax(0,1fr)_7rem_9rem_9rem_5.5rem]",
                  active ? "bg-ash-850" : "bg-ash-900 hover:bg-ash-850/70",
                )}
              >
                <span className="col-span-2 min-w-0 md:col-span-1">
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className={cn("h-3.5 w-[2px] rounded-xs", active ? "bg-sodium" : "bg-transparent")}
                    />
                    <span className="truncate font-mono text-[13px] font-medium text-bone">{p.name}</span>
                    <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.1em] text-bone-4">
                      {p.role}
                    </span>
                  </span>
                  <span className="mt-1 block pl-3.5 font-mono text-[11px] text-bone-4">{p.runtime}</span>
                </span>

                <span className="flex items-center gap-2">
                  <Dot tone={p.status} pulse={p.status !== "healthy"} />
                  <span
                    className={cn(
                      "font-mono text-[11.5px]",
                      p.status === "healthy"
                        ? "text-jade"
                        : p.status === "degraded"
                          ? "text-sodium"
                          : "text-brick",
                    )}
                  >
                    {STATUS_WORD[p.status]}
                  </span>
                </span>

                <Measure value={latest.cpu} warn={70} />
                <Measure value={latest.memory} warn={75} />

                <span className="flex items-center justify-between gap-2">
                  <span className="tnum text-[11.5px] text-bone-3">{duration(p.uptimeSeconds)}</span>
                  <span className="hidden w-10 lg:block">
                    <Sparkline
                      values={p.history.slice(-24).map((s) => s.cpu)}
                      color="var(--color-ash-600)"
                      height={14}
                      fill={false}
                    />
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
