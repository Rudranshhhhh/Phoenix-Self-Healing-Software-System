import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "../../lib/cn";
import { py } from "./py";

// ---------------------------------------------------------------------------
// Copy-to-clipboard, shared by the install command and every code pane.
// ---------------------------------------------------------------------------

function useCopy() {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return; // Clipboard blocked; the code is on screen either way.
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1800);
  }, []);

  return { copied, copy };
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const { copied, copy } = useCopy();
  return (
    <button
      type="button"
      onClick={() => void copy(text)}
      aria-label={copied ? "Copied" : label}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-xs border px-2 font-mono text-[10.5px] uppercase tracking-[0.12em] transition-colors",
        copied
          ? "border-jade/40 bg-jade/10 text-jade"
          : "border-ash-700 text-bone-3 hover:border-ash-600 hover:text-bone",
      )}
    >
      {copied ? <Check size={11} strokeWidth={2.5} /> : <Copy size={11} strokeWidth={2} />}
      {copied ? "Copied" : label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// The install command. One line, one job.
// ---------------------------------------------------------------------------

export function CommandLine({ command }: { command: string }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-ash-700 bg-ash-925 py-2.5 pl-4 pr-2.5">
      <span aria-hidden className="select-none font-mono text-[13px] text-bone-4">
        $
      </span>
      <code className="mono-pane flex-1 overflow-x-auto whitespace-nowrap text-bone">{command}</code>
      <CopyButton text={command} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// A tabbed Python pane with line numbers.
// ---------------------------------------------------------------------------

export interface Snippet {
  id: string;
  tab: string;
  filename: string;
  code: string;
}

export function CodePane({ snippets }: { snippets: Snippet[] }) {
  const [active, setActive] = useState(snippets[0].id);
  const current = snippets.find((s) => s.id === active) ?? snippets[0];
  const lines = current.code.split("\n");

  return (
    <div className="overflow-hidden rounded-md border border-ash-700 bg-ash-925">
      {/* Tabs sit on the same rule as the filename, like editor chrome. */}
      <div className="flex items-stretch border-b border-ash-800" role="tablist" aria-label="Framework">
        {snippets.map((s) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={s.id === active}
            onClick={() => setActive(s.id)}
            className={cn(
              "relative px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
              s.id === active ? "text-sodium" : "text-bone-3 hover:text-bone-2",
            )}
          >
            {s.tab}
            {s.id === active && <span className="absolute inset-x-0 -bottom-px h-px bg-sodium" />}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-3 pr-2.5">
          <span className="hidden font-mono text-[11px] text-bone-4 sm:inline">{current.filename}</span>
          <CopyButton text={current.code} />
        </div>
      </div>

      <div className="mono-pane overflow-x-auto py-3.5">
        {lines.map((line, i) => (
          <div key={i} className="flex px-0">
            <span
              aria-hidden
              className="tnum w-11 shrink-0 select-none pr-4 text-right text-[11px] text-bone-4"
            >
              {i + 1}
            </span>
            <code className="whitespace-pre pr-6">{line ? py(line) : " "}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
