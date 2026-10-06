import { Fragment } from "react";

type Node = { title: string; detail: string; external?: boolean };

const FIX_PATH: Node[] = [
  { title: "Your app", detail: "CI run or Docker container" },
  { title: "Orchestrator", detail: "agent/orchestrator" },
  { title: "LLM engine", detail: "Groq\ngpt-oss-120b", external: true },
  { title: "Sandbox", detail: "flake8 + pytest on a throwaway copy" },
  { title: "Git", detail: "fix branch, then a pull request" },
];
const FIX_EDGES = ["traceback", "code + error", "patch", "tests pass"];

const REPORT_PATH: Node[] = [
  { title: "Orchestrator", detail: "after every step" },
  { title: "phoenix-api", detail: "FastAPI · port 8000" },
  { title: "Dashboard", detail: "this site, checks every 2.5s" },
];
const REPORT_EDGES = ["POST /api/ingest/events", "GET /api/incidents"];

function Flow({ nodes, edges }: { nodes: Node[]; edges: string[] }) {
  return (
    <div className="flex flex-col md:flex-row md:items-stretch">
      {nodes.map((n, i) => (
        <Fragment key={n.title}>
          {i > 0 && (
            <div
              aria-hidden
              className="flex items-center gap-2 py-2 pl-4 md:flex-col md:justify-center md:gap-1 md:px-2 md:py-0"
            >
              <span className="font-mono text-[14px] text-ink md:hidden">↓</span>
              <span className="hidden font-mono text-[14px] text-ink md:inline">→</span>
              <span className="font-mono text-[11px] text-muted md:max-w-[9.5rem] md:break-normal md:text-center">
                {edges[i - 1]}
              </span>
            </div>
          )}
          <div
            className={`min-w-0 flex-1 rounded-box border bg-surface px-3 py-3 ${
              n.external ? "border-dashed border-muted" : "border-line"
            }`}
          >
            <p className="text-[14px] font-medium text-ink">{n.title}</p>
            <p className="mt-1 whitespace-pre-line text-[12.5px] leading-[1.5] text-muted">{n.detail}</p>
          </div>
        </Fragment>
      ))}
    </div>
  );
}

export function ArchitectureSketch() {
  return (
    <section aria-labelledby="arch-title" className="border-t border-line">
      <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 sm:py-20">
        <p className="text-[14px] font-medium text-muted">Under the hood</p>
        <h2 id="arch-title" className="mt-2 text-[clamp(1.6rem,3.2vw,2.2rem)] text-ink">
          Where the pieces run
        </h2>
        <p className="mt-3 max-w-[44rem] text-[16px] leading-[1.6] text-body">
          One orchestrator does the work. It reports each step to a small API, and this site reads from it. The
          dashed box is an outside service.
        </p>

        <div className="mt-8 space-y-8">
          <div>
            <p className="mb-3 font-mono text-[12px] text-muted">fix path</p>
            <Flow nodes={FIX_PATH} edges={FIX_EDGES} />
          </div>
          <div className="md:max-w-[62%]">
            <p className="mb-3 font-mono text-[12px] text-muted">reporting</p>
            <Flow nodes={REPORT_PATH} edges={REPORT_EDGES} />
          </div>
        </div>
      </div>
    </section>
  );
}
