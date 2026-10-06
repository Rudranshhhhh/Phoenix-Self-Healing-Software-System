import { useState } from "react";
import { Check, Copy } from "lucide-react";

const STEPS = [
  {
    label: "Start the API",
    note: "From the repo root, in its own terminal.",
    code: "cd phoenix-api\n.venv\\Scripts\\activate\nuvicorn app.main:app --port 8000",
  },
  {
    label: "Start the dashboard",
    note: "Second terminal.",
    code: "cd frontend\nnpm run dev",
  },
  {
    label: "Break the demo app",
    note: "Third terminal, with Docker Desktop running.",
    code: ".venv\\Scripts\\python.exe -m agent.orchestrator demo\\broken_app",
  },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked: do nothing */
        }
      }}
      aria-label={copied ? "Copied" : "Copy commands"}
      className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-box border border-line bg-surface px-2 text-[12px] font-medium text-ink hover:border-line-strong"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export function TryIt() {
  return (
    <section id="try" aria-labelledby="try-title" className="scroll-mt-24 border-t border-line">
      <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 sm:py-20">
        <p className="text-[14px] font-medium text-muted">Try it</p>
        <h2 id="try-title" className="mt-2 text-[clamp(1.6rem,3.2vw,2.2rem)] text-ink">
          Run it on your laptop
        </h2>
        <p className="mt-3 max-w-[44rem] text-[16px] leading-[1.6] text-body">
          Three terminals in PowerShell. You need Python 3.11, Node, Docker Desktop and a Groq API key in{" "}
          <code className="font-mono text-[14px]">.env</code>. Then open localhost:3000 and watch the incident come in.
        </p>

        <ol className="mt-8 grid gap-4 lg:grid-cols-3">
          {STEPS.map((s, i) => (
            <li
              key={s.label}
              className="flex min-w-0 flex-col overflow-hidden rounded-box border border-line bg-surface"
            >
              <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
                <div className="min-w-0">
                  <p className="flex items-baseline gap-2 text-[14px] font-medium text-ink">
                    <span className="font-mono text-[12px] text-muted">0{i + 1}</span>
                    {s.label}
                  </p>
                  <p className="mt-0.5 text-[12.5px] text-muted">{s.note}</p>
                </div>
                <CopyButton text={s.code} />
              </div>
              <pre className="flex-1 overflow-x-auto bg-code px-4 py-3 font-mono text-[12.5px] leading-[1.7] text-body">
                {s.code}
              </pre>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
