import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// A small Python highlighter. Deliberately not a dependency: the only code
// this app renders is short Python snippets, tracebacks, and diff hunks, and
// hand-rolling it keeps the palette under our control.
// ---------------------------------------------------------------------------

const KEYWORDS =
  "from|import|def|class|return|if|elif|else|for|while|try|except|finally|with|as|raise|yield|async|await|lambda|pass|break|continue|global|nonlocal|assert|del|in|is|not|and|or|None|True|False|self";

const PATTERN = new RegExp(
  [
    "(#[^\\n]*)", // 1 comment
    "(\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?'''|f?\"(?:[^\"\\\\]|\\\\.)*\"|f?'(?:[^'\\\\]|\\\\.)*')", // 2 string
    "(@[A-Za-z_][\\w.]*)", // 3 decorator
    `\\b(${KEYWORDS})\\b`, // 4 keyword
    "\\b(\\d+\\.?\\d*)\\b", // 5 number
    "\\b([A-Za-z_]\\w*)(?=\\()", // 6 call
  ].join("|"),
  "g",
);

const STYLES = [
  "", // 0 unused
  "italic text-[var(--color-code-cmt)]",
  "text-[var(--color-code-lit)]",
  "text-sodium",
  "text-[var(--color-code-kw)]",
  "text-[var(--color-code-lit)]",
  "text-bone",
];

/** Highlight one line of Python. Returns plain text nodes plus coloured spans. */
export function py(code: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;

  PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = PATTERN.exec(code)) !== null) {
    if (match.index > last) out.push(code.slice(last, match.index));
    const group = match.findIndex((value, index) => index > 0 && value !== undefined);
    out.push(
      <span key={`t${key++}`} className={STYLES[group]}>
        {match[0]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  if (last < code.length) out.push(code.slice(last));
  return out;
}
