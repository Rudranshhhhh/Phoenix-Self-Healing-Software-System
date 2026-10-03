import { useId } from "react";

export type ChickMood =
  | "alert" | "dizzy" | "thinking" | "focused"
  | "smile" | "happy" | "neutral" | "asleep";

type Props = {
  mood: ChickMood;
  size?: number;
  variant?: "soft" | "flat";
  className?: string;
};

const BODY = "M15 47C13 37 20 26 32 26C44 26 51 37 49 47C48 54 41 56.5 32 56.5C23 56.5 16 54 15 47Z";
const CREST = "M31 26.5C28 21 29 14 34 8C33.5 13 36 17 35.5 21C35 23.5 34.2 25.2 33.6 26.5ZM27.5 27.5C24 25 23.5 20.5 25.5 17C26.5 20.5 29 22.5 30 26ZM36.5 27C38.8 23 41.8 21 45.5 20.5C44 23.5 41.5 26 39 28Z";
const TAIL = "M47 51C54 51.5 60 49 63 45C62 51 56 55 48 55ZM45 54C51 58 57 58.5 61 57C57 60 50 60 44 57Z";
const WINGS = "M15 38C8 36 3.5 40 4.5 46.5C6.3 45 7.6 46 8.2 47.6C9.6 46 11 47 11.6 48.6C12.6 47 14 46.5 15.5 46.5ZM49 38C56 36 60.5 40 59.5 46.5C57.7 45 56.4 46 55.8 47.6C54.4 46 53 47 52.4 48.6C51.4 47 50 46.5 48.5 46.5Z";
const BEAK = "M30 38.6Q32 37.9 34 38.6L32 41.6Z";
const FEET = "M28.5 56.5v2.4M35.5 56.5v2.4";

const WARM = {
  body: ["#FF9A5E", "#FFC9A8", "#FFF6EF"],
  flame: ["#FF4F12", "#FFB27A"],
  wing: "#FFAE85", halo: "#FFDCC6", beak: "#F2763A",
};
const COOL = {
  body: ["#B8B0A9", "#DAD3CD", "#F8F5F2"],
  flame: ["#968C85", "#CDC5BE"],
  wing: "#C9C1BA", halo: "#E6E0DA", beak: "#A39C96",
};

const MOTION: Partial<Record<ChickMood, string>> = {
  alert: "chick-hop", smile: "chick-hop", happy: "chick-hop", dizzy: "chick-wob",
};

const line = {
  fill: "none", stroke: "#000", strokeWidth: 1.3,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

const spiral = (cx: number, cy = 35.5) => {
  let d = "";
  for (let i = 0; i <= 24; i++) {
    const t = i * 0.4;
    const r = 0.38 * t;
    const x = cx + r * Math.cos(t);
    const y = cy + r * Math.sin(t);
    d += (i ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2);
  }
  return d;
};

function Face({ mood }: { mood: ChickMood }) {
  switch (mood) {
    case "alert":
      return (<>
        <circle cx={25} cy={35.5} r={1.7} fill="#000" />
        <circle cx={39} cy={35.5} r={1.7} fill="#000" />
        <circle cx={32} cy={44.2} r={1} {...line} />
        <path className="chick-pop" d="M55 3v6" {...line} />
        <circle className="chick-pop" cx={55} cy={12} r={1} fill="#000" />
      </>);
    case "dizzy":
      return (<>
        <path className="chick-spin" d={spiral(25)} {...line} strokeWidth={1.1} />
        <path className="chick-spin" d={spiral(39)} {...line} strokeWidth={1.1} />
        <path d="M29.6 44.4q.6-.9 1.2 0t1.2 0t1.2 0t1.2 0" {...line} />
        <circle className="chick-pop" cx={12} cy={18} r={1.1} fill="#000" />
        <circle className="chick-pop2" cx={54} cy={12} r={1.1} fill="#000" />
      </>);
    case "thinking":
      return (<>
        <circle cx={26} cy={34.6} r={1.4} fill="#000" />
        <circle cx={40} cy={34.6} r={1.4} fill="#000" />
        <path d="M31 44.2h2" {...line} />
        <circle className="chick-pop" cx={51} cy={15} r={1.1} fill="#000" />
        <circle className="chick-pop2" cx={56} cy={8.5} r={2.2} {...line} />
      </>);
    case "focused":
      return (<>
        <path d="M23 36h4M37 36h4" {...line} />
        <path d="M31 44.2h2" {...line} />
      </>);
    case "smile":
      return (<>
        <circle className="chick-blink" cx={25} cy={35.5} r={1.4} fill="#000" />
        <circle className="chick-blink" cx={39} cy={35.5} r={1.4} fill="#000" />
        <path d="M30.6 43.6q1.4 1.4 2.8 0" {...line} />
      </>);
    case "happy":
      return (<>
        <path d="M23 36.5l2-2l2 2M37 36.5l2-2l2 2" {...line} />
        <path d="M30.2 43.2h3.6q-1.8 2.8-3.6 0z" {...line} />
        <path className="chick-pop" d="M55 4v5M52.5 6.5h5" {...line} />
        <path className="chick-pop2" d="M9 14v4M7 16h4" {...line} />
      </>);
    case "neutral":
      return (<>
        <circle cx={25} cy={35.5} r={1.4} fill="#000" />
        <circle cx={39} cy={35.5} r={1.4} fill="#000" />
        <path d="M31 44.2h2" {...line} />
      </>);
    case "asleep":
      return (<>
        <path d="M23 35.5q2 1.6 4 0M37 35.5q2 1.6 4 0" {...line} />
        <path className="chick-zz" d="M48 6h5l-5 6h5M55 14h3.5l-3.5 4h3.5" {...line} />
      </>);
  }
}

/** Phoenix mascot. Warm while Phoenix is working; warm grey when asleep or rejected (neutral). */
export function PhoenixChick({ mood, size = 96, variant = "soft", className }: Props) {
  const uid = useId().replace(/:/g, "");
  const cool = mood === "neutral" || mood === "asleep";
  const c = cool ? COOL : WARM;
  const blush = mood === "neutral" ? 0 : mood === "asleep" ? 0.35 : 0.55;
  const flatFlame = cool ? "#fff" : "#FF4F12";

  return (
    <span
      key={mood}
      aria-hidden="true"
      className={["inline-block align-top", MOTION[mood] ?? "", className ?? ""].join(" ")}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox="0 0 64 64" overflow="visible">
        {variant === "soft" ? (
          <>
            <defs>
              <linearGradient id={`${uid}-b`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={c.body[0]} />
                <stop offset="0.55" stopColor={c.body[1]} />
                <stop offset="1" stopColor={c.body[2]} />
              </linearGradient>
              <linearGradient id={`${uid}-f`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={c.flame[0]} />
                <stop offset="1" stopColor={c.flame[1]} />
              </linearGradient>
            </defs>
            <ellipse cx={33} cy={59} rx={18} ry={2.6} fill="#000" opacity={0.06} />
            <ellipse cx={33} cy={59} rx={12} ry={1.6} fill="#000" opacity={0.08} />
            <path d={TAIL} fill={`url(#${uid}-f)`} />
            <path d={CREST} fill={`url(#${uid}-f)`} />
            <path d={FEET} fill="none" stroke={c.beak} strokeWidth={1.5} strokeLinecap="round" />
            <path d={BODY} fill="none" stroke={c.halo} strokeWidth={3.2} strokeLinejoin="round" opacity={0.6} />
            <path d={BODY} fill={`url(#${uid}-b)`} />
            <ellipse cx={32} cy={49} rx={10} ry={5.5} fill="#fff" opacity={0.5} />
            <path d={WINGS} fill={c.wing} opacity={0.92} />
            {blush > 0 && (
              <>
                <ellipse cx={21.5} cy={40} rx={2.8} ry={1.4} fill="#F7A1B8" opacity={blush} />
                <ellipse cx={42.5} cy={40} rx={2.8} ry={1.4} fill="#F7A1B8" opacity={blush} />
              </>
            )}
            <path d={BEAK} fill={c.beak} />
            <circle cx={43} cy={30} r={1.3} fill="#fff" />
            <circle cx={44.9} cy={29} r={0.6} fill="#fff" />
          </>
        ) : (
          <>
            <ellipse cx={33} cy={59} rx={16} ry={2} fill="#000" opacity={0.1} />
            <path d={TAIL} fill={flatFlame} stroke="#000" strokeWidth={1.4} strokeLinejoin="round" />
            <path d={CREST} fill={flatFlame} stroke="#000" strokeWidth={1.4} strokeLinejoin="round" />
            <path d={FEET} fill="none" stroke="#000" strokeWidth={1.4} strokeLinecap="round" />
            <path d={BODY} fill="#fff" stroke="#000" strokeWidth={1.6} strokeLinejoin="round" />
            <path d={WINGS} fill="#fff" stroke="#000" strokeWidth={1.6} strokeLinejoin="round" />
            <path d={BEAK} fill={flatFlame} stroke="#000" strokeWidth={1.1} strokeLinejoin="round" />
          </>
        )}
        <Face mood={mood} />
      </svg>
    </span>
  );
}
