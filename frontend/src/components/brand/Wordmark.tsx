import type { CSSProperties } from "react";

/**
 * The Phoenix mark: a minus above a plus. What was removed, what replaced it —
 * the whole product in two strokes, and the only glyph the brand needs.
 */
export function Mark({ size = 22, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <rect x="0.6" y="0.6" width="22.8" height="22.8" rx="4" stroke="currentColor" strokeOpacity="0.28" />
      <path d="M6.5 9h11" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.7" strokeLinecap="round" />
      <path
        d="M6.5 15.5h11M12 10v11"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeDasharray="0 0"
        clipPath="url(#phx-clip)"
      />
      <defs>
        <clipPath id="phx-clip">
          <rect x="0" y="11.6" width="24" height="12.4" />
        </clipPath>
      </defs>
    </svg>
  );
}

export function Wordmark({ style }: { style?: CSSProperties }) {
  return (
    <span className="font-dot font-extrabold text-[26px] leading-none tracking-[0.02em] text-ink" style={style}>
      Phoenix
    </span>
  );
}

/** GitHub's mark. lucide dropped brand icons, and this keeps the stroke ours. */
export function GithubMark({ size = 15, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="currentColor"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.05-.13-.36-.66.05-1.36 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.41.7.1 1.23.05 1.36.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A7.995 7.995 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}
