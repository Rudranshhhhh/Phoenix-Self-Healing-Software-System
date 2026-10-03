import { useState } from "react";
import { PhoenixChick, type ChickMood } from "../components/phoenix/PhoenixChick";

const MOODS: ChickMood[] = ["alert", "dizzy", "thinking", "focused", "smile", "happy", "neutral", "asleep"];
const VARIANTS = [
  { variant: "soft", label: "Soft" },
  { variant: "flat", label: "Flat" },
] as const;

/** Dev-only gallery of every mood, at /dev/chick. */
export default function ChickPreview() {
  const [run, setRun] = useState(0);

  return (
    <div className="min-h-screen bg-page p-6">
      <h1 className="text-2xl font-semibold text-ink">Phoenix chick</h1>
      <button
        type="button"
        onClick={() => setRun((n) => n + 1)}
        className="mt-4 h-8 rounded-box border border-line bg-surface px-3 text-sm"
      >
        Replay reactions
      </button>

      <div key={run}>
        {VARIANTS.map(({ variant, label }) => (
          <section key={variant} className="mt-8">
            <h2 className="text-sm text-muted">{label}</h2>
            <div className="mt-3 flex flex-wrap gap-6">
              {MOODS.map((mood) => (
                <figure key={mood} className="m-0 flex flex-col items-center gap-2">
                  <PhoenixChick mood={mood} size={96} variant={variant} />
                  <figcaption className="text-xs text-muted">{mood}</figcaption>
                </figure>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
