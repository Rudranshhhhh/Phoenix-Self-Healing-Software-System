import { useId } from "react";

// ---------------------------------------------------------------------------
// Hand-rolled SVG charts. Small enough not to want a charting library, and it
// keeps the stroke weights and the palette consistent with everything else.
// ---------------------------------------------------------------------------

function path(values: number[], w: number, h: number, min: number, max: number): string {
  if (values.length < 2) return "";
  const span = max - min || 1;
  const step = w / (values.length - 1);
  return values
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

interface SparkProps {
  values: number[];
  color?: string;
  height?: number;
  /** Draw a filled area under the line. */
  fill?: boolean;
}

export function Sparkline({ values, color = "var(--color-bone-2)", height = 30, fill = true }: SparkProps) {
  const id = useId();
  const w = 120;
  const h = height;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.18 || 1;
  const line = path(values, w, h, min - pad, max + pad);

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      width="100%"
      height={h}
      aria-hidden="true"
      className="block overflow-visible"
    >
      {fill && (
        <>
          <defs>
            <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.22" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${line} L${w},${h} L0,${h} Z`} fill={`url(#g${id})`} />
        </>
      )}
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

interface TrendProps {
  values: number[];
  color?: string;
  height?: number;
  /** Horizontal reference line, e.g. an alert threshold. */
  threshold?: number;
  unit?: string;
  /** Fix the vertical range instead of fitting the data. */
  domain?: [number, number];
}

export function Trend({
  values,
  color = "var(--color-sodium)",
  height = 168,
  threshold,
  unit = "",
  domain,
}: TrendProps) {
  const id = useId();
  const w = 600;
  const h = height;
  const lo = domain ? domain[0] : Math.min(...values) * 0.85;
  const hi = domain ? domain[1] : Math.max(...values) * 1.12 || 1;
  const line = path(values, w, h, lo, hi);
  const ticks = [hi, lo + (hi - lo) / 2, lo];
  const thresholdY = threshold !== undefined ? h - ((threshold - lo) / (hi - lo || 1)) * h : null;

  return (
    <div className="relative">
      {/* Value axis, in the left margin like a ledger's figures column. */}
      <div className="pointer-events-none absolute inset-y-0 left-0 flex w-12 flex-col justify-between">
        {ticks.map((t) => (
          <span key={t} className="tnum text-[10px] leading-none text-bone-4">
            {t >= 100 ? Math.round(t) : t.toFixed(t < 10 ? 1 : 0)}
            {unit}
          </span>
        ))}
      </div>

      <div className="ml-12">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          preserveAspectRatio="none"
          width="100%"
          height={h}
          aria-hidden="true"
          className="block"
        >
          <defs>
            <linearGradient id={`t${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.26" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>

          {[0, 0.5, 1].map((f) => (
            <line
              key={f}
              x1="0"
              x2={w}
              y1={f * h}
              y2={f * h}
              stroke="var(--color-ash-800)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          {thresholdY !== null && thresholdY > 0 && thresholdY < h && (
            <line
              x1="0"
              x2={w}
              y1={thresholdY}
              y2={thresholdY}
              stroke="var(--color-brick)"
              strokeOpacity="0.45"
              strokeWidth="1"
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
          )}

          <path d={`${line} L${w},${h} L0,${h} Z`} fill={`url(#t${id})`} />
          <path
            d={line}
            fill="none"
            stroke={color}
            strokeWidth="1.75"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
    </div>
  );
}
