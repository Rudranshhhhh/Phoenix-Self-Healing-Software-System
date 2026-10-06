import { useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import { PhoenixChick, type ChickMood } from "../phoenix/PhoenixChick";
import { Button } from "../ui/Button";

const STEP_MS = 3200;

type Tone = "fail" | "pass" | "muted" | "add" | "del";
type Line = { text: string; tone?: Tone; sans?: boolean; note?: string };
type Frame = {
  label: string;
  title: string;
  source: string;
  mood: ChickMood;
  acting: boolean; // Ember only while Phoenix is acting
  lines: Line[];
};

// Real data from INC-109 (phoenix-api/data/incidents.json, 5 Oct 2026)
const FRAMES: Frame[] = [
  {
    label: "CI fails",
    title: "The app crashes on a request",
    source: "docker · phoenix-run-broken_app",
    mood: "alert",
    acting: false,
    lines: [
      { text: "Traceback (most recent call last):", tone: "muted" },
      { text: '  File "/app/app.py", line 9, in get_product' },
      { text: '    return product["price"]', note: "this line broke the build" },
      { text: "KeyError: 'price'", tone: "fail" },
    ],
  },
  {
    label: "Reads it",
    title: "Phoenix finds the root cause",
    source: "diagnosis · app.py:9 · confidence 0.99",
    mood: "thinking",
    acting: true,
    lines: [
      {
        sans: true,
        text: 'PRODUCTS defines each product with a "cost" field, but get_product() looks up product["price"].',
      },
      { sans: true, tone: "muted", text: "The code reads a key that doesn't exist." },
    ],
  },
  {
    label: "Writes a patch",
    title: "It writes the smallest fix",
    source: "app.py",
    mood: "focused",
    acting: true,
    lines: [
      { text: "@@ line 9 @@", tone: "muted" },
      { text: '-    return product["price"]', tone: "del" },
      { text: '+    return product["cost"]', tone: "add", note: "one line changed" },
    ],
  },
  {
    label: "Tests it",
    title: "Then runs the tests in a sandbox",
    source: "sandbox · pytest",
    mood: "smile",
    acting: true,
    lines: [
      { text: "$ pytest -q", tone: "muted" },
      { text: "test_app.py::test_get_product_apple_does_not_raise PASSED" },
      { text: "1 passed in 2.45s", tone: "pass", note: "this test crashed before the fix" },
    ],
  },
  {
    label: "Ready for review",
    title: "The fix waits for a person",
    source: "git · local workspace",
    mood: "happy",
    acting: false,
    lines: [
      { text: "branch  phoenix/fix/INC-109", note: "not pushed yet" },
      { text: "status  validated · 8s from crash to tested fix" },
      {
        sans: true,
        tone: "muted",
        text: "On a connected repository, this is where Phoenix opens the pull request.",
      },
    ],
  },
];

function lineClass(line: Line) {
  const base = line.sans
    ? "text-[14.5px] leading-[1.6]"
    : "font-mono text-[12.5px] leading-[1.7] whitespace-pre-wrap [overflow-wrap:anywhere]";
  switch (line.tone) {
    case "fail":
      return `${base} text-fail`;
    case "pass":
      return `${base} text-pass`;
    case "muted":
      return `${base} text-muted`;
    case "add":
      return `${base} -mx-2 bg-add-bg px-2 text-body`;
    case "del":
      return `${base} -mx-2 bg-del-bg px-2 text-body`;
    default:
      return `${base} text-body`;
  }
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

export function HealReplay() {
  const reduced = usePrefersReducedMotion();
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(!reduced);
  const [inView, setInView] = useState(false);
  const ref = useRef<HTMLElement>(null);

  // reduced motion: never autoplay, steps are still clickable
  useEffect(() => {
    if (reduced) setPlaying(false);
  }, [reduced]);

  // only run while the section is on screen
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const running = playing && inView;

  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(() => setStep((s) => (s + 1) % FRAMES.length), STEP_MS);
    return () => window.clearTimeout(t);
  }, [running, step]);

  const frame = FRAMES[step];

  return (
    <section
      ref={ref}
      aria-labelledby="replay-title"
      className="mx-auto max-w-[1200px] px-4 pb-16 sm:px-6 sm:pb-20"
    >
      <div className="mb-6 max-w-[44rem]">
        <p className="text-[14px] font-medium text-muted">
          Replay · <span className="font-dot">INC-109</span>
        </p>
        <h2 id="replay-title" className="mt-2 text-[clamp(1.6rem,3.2vw,2.2rem)] text-ink">
          What one fix looked like
        </h2>
        <p className="mt-3 text-[16px] leading-[1.6] text-body">
          A real run from the demo app on 5 October. An endpoint crashed, and about 8 seconds later Phoenix had a
          tested fix on its own branch.
        </p>
      </div>

      <div className="grid gap-4 rounded-box border border-line bg-surface p-4 sm:p-6 md:grid-cols-[220px_1fr] md:gap-6">
        {/* steps */}
        <div className="flex flex-col gap-4">
          <ol className="grid grid-cols-5 gap-2 md:grid-cols-1 md:gap-1">
            {FRAMES.map((f, i) => {
              const active = i === step;
              return (
                <li key={f.label}>
                  <button
                    type="button"
                    onClick={() => {
                      setStep(i);
                      setPlaying(false);
                    }}
                    aria-current={active ? "step" : undefined}
                    aria-label={`Step ${i + 1}: ${f.label}`}
                    className={`relative w-full overflow-hidden rounded-box border px-2 py-2 text-left md:px-3 ${
                      active ? "border-ink bg-page text-ink" : "border-transparent text-muted hover:text-ink"
                    }`}
                  >
                    <span className="block font-mono text-[12px]">0{i + 1}</span>
                    <span className="hidden text-[14px] font-medium md:block">{f.label}</span>
                    {active && running && (
                      <span
                        key={step}
                        aria-hidden
                        className={`heal-bar absolute inset-x-0 bottom-0 h-[2px] ${f.acting ? "bg-ember" : "bg-ink"}`}
                        style={{ animationDuration: `${STEP_MS}ms` }}
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setPlaying((p) => !p)}>
              {playing ? <Pause size={14} /> : <Play size={14} />}
              {playing ? "Pause" : "Play"}
            </Button>
            <Button
              size="sm"
              tone="ghost"
              onClick={() => {
                setStep(0);
                setPlaying(true);
              }}
            >
              <RotateCcw size={14} />
              Replay
            </Button>
          </div>
        </div>

        {/* screen */}
        <div className="min-w-0 rounded-box border border-line bg-code">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2">
            <span className="truncate font-mono text-[12px] text-muted">{frame.source}</span>
            <span className="shrink-0 text-[12px] font-medium text-muted md:hidden">{frame.label}</span>
          </div>
          <div className="flex items-start gap-4 p-4 sm:p-5">
            <div key={step} className="min-h-[150px] min-w-0 flex-1">
              <p className="heal-line mb-3 text-[15px] font-medium text-ink">{frame.title}</p>
              {frame.lines.map((line, i) => (
                <div
                  key={i}
                  className={`heal-line flex items-baseline gap-6 ${lineClass(line)}`}
                  style={{ animationDelay: `${150 + i * 220}ms` }}
                >
                  <span className="min-w-0">{line.text}</span>
                  {line.note && (
                    <span className="hidden shrink-0 font-sans text-[12px] italic text-muted md:inline">
                      ← {line.note}
                    </span>
                  )}
                </div>
              ))}
            </div>
            <PhoenixChick mood={frame.mood} size={44} className="shrink-0" />
          </div>
        </div>
      </div>
    </section>
  );
}
