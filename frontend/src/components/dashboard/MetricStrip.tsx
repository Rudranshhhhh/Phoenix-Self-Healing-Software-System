import type { ServiceProcess } from "../../types/phoenix";
import { Sparkline } from "../charts/Chart";
import { Label } from "../ui/Primitives";
import { cn } from "../../lib/cn";

// ---------------------------------------------------------------------------
// The five figures that matter, ruled into one strip rather than five cards.
// ---------------------------------------------------------------------------

type Key = "cpu" | "memory" | "rpm" | "p95" | "errorRate";

interface Column {
  key: Key;
  label: string;
  unit: string;
  digits: number;
  /** Above this, the figure turns amber; twice this, brick. */
  warn: number;
}

const COLUMNS: Column[] = [
  { key: "cpu", label: "CPU", unit: "%", digits: 1, warn: 70 },
  { key: "memory", label: "Memory", unit: "%", digits: 1, warn: 75 },
  { key: "rpm", label: "Requests", unit: "/min", digits: 0, warn: Infinity },
  { key: "p95", label: "p95 latency", unit: "ms", digits: 0, warn: 400 },
  { key: "errorRate", label: "Error rate", unit: "%", digits: 2, warn: 1 },
];

function tone(value: number, warn: number) {
  if (value >= warn * 1.35) return { text: "text-brick", stroke: "var(--color-brick)" };
  if (value >= warn) return { text: "text-sodium", stroke: "var(--color-sodium)" };
  return { text: "text-bone", stroke: "var(--color-bone-2)" };
}

export function MetricStrip({ process }: { process: ServiceProcess }) {
  const latest = process.history[process.history.length - 1];

  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-ash-800 bg-ash-800 sm:grid-cols-3 lg:grid-cols-5">
      {COLUMNS.map((col) => {
        const series = process.history.map((s) => s[col.key]);
        const value = latest[col.key];
        const prior = series.slice(-24, -4);
        const mean = prior.reduce((a, b) => a + b, 0) / (prior.length || 1);
        const delta = value - mean;
        const t = tone(value, col.warn);

        return (
          <div key={col.key} className="flex flex-col justify-between bg-ash-900 px-4 pb-3 pt-3.5">
            <div className="flex items-baseline justify-between gap-2">
              <Label>{col.label}</Label>
              {Math.abs(delta) > Math.max(0.05, mean * 0.06) && (
                <span
                  className={cn(
                    "tnum text-[10px]",
                    delta > 0 ? "text-bone-3" : "text-bone-4",
                  )}
                >
                  {delta > 0 ? "▲" : "▼"}
                  {Math.abs(delta) >= 10 ? Math.abs(delta).toFixed(0) : Math.abs(delta).toFixed(1)}
                </span>
              )}
            </div>

            <div className="mt-2.5 flex items-baseline gap-1">
              <span className={cn("tnum text-[26px] leading-none tracking-tight", t.text)}>
                {value.toFixed(col.digits)}
              </span>
              <span className="font-mono text-[11px] text-bone-4">{col.unit}</span>
            </div>

            <div className="mt-3 -mb-0.5">
              <Sparkline values={series.slice(-40)} color={t.stroke} height={26} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function MemoryFootnote({ process }: { process: ServiceProcess }) {
  const latest = process.history[process.history.length - 1];
  return (
    <span className="tnum text-[11.5px] text-bone-4">
      {latest.memoryMb} MB of {process.memoryLimitMb} MB · pid {process.pid} · {process.runtime}
    </span>
  );
}
