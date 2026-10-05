import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Lock, RefreshCw, Search } from "lucide-react";
import { GithubMark } from "../components/brand/Wordmark";
import type { Repository, SdkScan } from "../types/phoenix";
import { repositoriesPending, scanResult } from "../mock/repos";
import { useSession } from "../state/SessionContext";
import { since } from "../lib/format";
import { cn } from "../lib/cn";
import { Button } from "../components/ui/Button";

// ---------------------------------------------------------------------------

const SCOPES = [
  {
    scope: "contents: read",
    why: "Clone the repository you pick into a sandbox, so Phoenix can read the code in your traceback.",
  },
  {
    scope: "actions: read",
    why: "Read your CI runs and their logs, so Phoenix knows when a test fails and why.",
  },
  {
    scope: "pull_requests: write",
    why: "Push a phoenix/fix branch and open a pull request. Phoenix cannot merge one.",
  },
  {
    scope: "metadata: read",
    why: "List your repositories so you can choose which one to watch.",
  },
];

const WORKFLOW_PATH = ".github/workflows/tests.yml";

const WORKFLOW = `name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest`;

// ---------------------------------------------------------------------------
// Small light helpers
// ---------------------------------------------------------------------------

function StepLabel({ children }: { children: ReactNode }) {
  return <p className="text-[14px] font-medium text-muted">{children}</p>;
}

function Tag({ tone = "neutral", children }: { tone?: "neutral" | "pass"; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-box border px-2 py-0.5 text-[12px] font-medium",
        tone === "pass" ? "border-pass/30 bg-add-bg text-pass" : "border-line bg-subtle text-body",
      )}
    >
      {children}
    </span>
  );
}

/** Ember while Phoenix is scanning, green when done. */
function ScanDot({ working }: { working: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn("size-2 shrink-0 rounded-full", working ? "animate-pulse bg-ember" : "bg-pass")}
    />
  );
}

// ---------------------------------------------------------------------------
// Sign in
// ---------------------------------------------------------------------------

function SignIn({ onDone }: { onDone: () => void }) {
  const [pending, setPending] = useState(false);

  return (
    <div className="mx-auto max-w-[34rem] px-4 py-16 sm:px-6 sm:py-24">
      <StepLabel>Step one of two</StepLabel>
      <h1 className="mt-3 text-[clamp(1.9rem,4.6vw,2.7rem)] text-ink">Connect your GitHub account.</h1>
      <p className="mt-4 text-[15.5px] leading-relaxed text-body">
        Phoenix needs to read your CI runs and the code behind a failing test, and open pull requests with the
        fix. Here is exactly what it asks for.
      </p>

      <ul className="mt-8 list-none divide-y divide-line rounded-box border border-line bg-surface p-0">
        {SCOPES.map((s) => (
          <li key={s.scope} className="p-5">
            <code className="font-mono text-[13px] font-medium text-ink">{s.scope}</code>
            <p className="mt-1.5 text-[14px] leading-relaxed text-body">{s.why}</p>
          </li>
        ))}
      </ul>

      <p className="mt-5 text-[13.5px] leading-relaxed text-muted">
        It never asks for organization admin, and never asks for permission to push to your default branch.
        You choose the repository on the next screen.
      </p>

      <Button
        tone="primary"
        size="lg"
        className="mt-8 w-full"
        disabled={pending}
        onClick={() => {
          setPending(true);
          window.setTimeout(onDone, 850);
        }}
      >
        {pending ? (
          <>
            <RefreshCw size={16} className="animate-spin" />
            Opening GitHub…
          </>
        ) : (
          <>
            <GithubMark size={16} />
            Continue with GitHub
          </>
        )}
      </Button>

      <p className="mt-4 text-center text-[12px] text-muted">
        This build signs you in locally. No request leaves your browser.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scan status cell
// ---------------------------------------------------------------------------

function ScanCell({ scan, python }: { scan: SdkScan; python: boolean }) {
  switch (scan.state) {
    case "pending":
      return <span className="text-[13px] text-muted">Queued</span>;
    case "scanning":
      return (
        <span className="inline-flex items-center gap-2 text-[13px] text-body">
          <ScanDot working />
          Reading workflows
        </span>
      );
    case "installed":
    case "outdated":
      return (
        <span className="flex min-w-0 flex-col items-start gap-1">
          <Tag tone="pass">CI found</Tag>
          <span className="max-w-full truncate font-mono text-[11.5px] text-muted">{scan.foundIn}</span>
        </span>
      );
    case "missing":
      return (
        <span className="flex flex-col items-start gap-1">
          <Tag>{python ? "No CI workflow" : "Not a Python service"}</Tag>
          <span className="text-[12px] text-muted">
            {python ? "Nothing in .github/workflows" : "No Python code to test"}
          </span>
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Repository picker
// ---------------------------------------------------------------------------

function Picker() {
  const { user, selectRepo, signOut } = useSession();
  const navigate = useNavigate();

  const [repos, setRepos] = useState<Repository[]>(repositoriesPending);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<number | null>(null);
  const [rescanning, setRescanning] = useState<number | null>(null);
  const timers = useRef<Array<ReturnType<typeof setTimeout>>>([]);

  const patch = useCallback((id: number, scan: SdkScan) => {
    setRepos((prev) => prev.map((r) => (r.id === id ? { ...r, scan } : r)));
  }, []);

  // Walk the list one repository at a time.
  useEffect(() => {
    const seeds = repositoriesPending();
    seeds.forEach((repo, i) => {
      const at = 260 + i * 300;
      timers.current.push(setTimeout(() => patch(repo.id, { state: "scanning" }), at));
      timers.current.push(setTimeout(() => patch(repo.id, scanResult(repo.id)), at + 540));
    });
    const all = timers.current;
    return () => all.forEach(clearTimeout);
  }, [patch]);

  const done = repos.filter((r) => r.scan.state !== "pending" && r.scan.state !== "scanning").length;
  const scanning = done < repos.length;

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter((r) => `${r.owner}/${r.name} ${r.description}`.toLowerCase().includes(q));
  }, [repos, query]);

  const selected = repos.find((r) => r.id === chosen) ?? null;
  const ready = selected?.scan.state === "installed" || selected?.scan.state === "outdated";

  const rescan = (repo: Repository) => {
    setRescanning(repo.id);
    patch(repo.id, { state: "scanning" });
    window.setTimeout(() => {
      // Simulates the developer having added the workflow and pushed.
      patch(repo.id, { state: "installed", version: "0.4.2", foundIn: WORKFLOW_PATH, line: 1 });
      setRescanning(null);
    }, 1100);
  };

  const open = () => {
    if (!selected || !ready) return;
    selectRepo(selected);
    navigate(`/app/${selected.owner}/${selected.name}`);
  };

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-14 sm:px-6 sm:py-20">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <StepLabel>Step two of two</StepLabel>
          <h1 className="mt-3 text-[clamp(1.8rem,4vw,2.4rem)] text-ink">Pick a repository to watch.</h1>
          <p className="mt-4 max-w-[40rem] text-[15px] leading-relaxed text-body">
            Phoenix looks in each repository's <code className="font-mono text-[13.5px] text-ink">.github/workflows</code>{" "}
            folder for a CI run that tests your Python code. A repository without one has nothing for Phoenix to
            watch yet.
          </p>
        </div>

        <div className="flex items-center gap-3 rounded-box border border-line bg-surface px-4 py-2.5">
          <span className="grid size-7 place-items-center rounded-box bg-subtle font-mono text-[11px] text-body">
            {user?.login.slice(0, 2).toUpperCase()}
          </span>
          <span className="text-[13px] text-ink">{user?.login}</span>
          <button
            type="button"
            onClick={signOut}
            className="ml-2 text-[13px] text-muted transition-colors hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* scan progress + search */}
      <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
        <span className="flex items-center gap-2.5 text-[13px] font-medium text-body">
          <ScanDot working={scanning} />
          {scanning ? `Scanning ${done}/${repos.length}` : `${repos.length} repositories scanned`}
        </span>

        <div className="relative ml-auto w-full sm:w-72">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter repositories"
            aria-label="Filter repositories"
            className="h-10 w-full rounded-box border border-line bg-surface pl-9 pr-3 text-[14px] text-ink placeholder:text-muted focus:border-ink focus:outline-none"
          />
        </div>
      </div>

      {/* the list */}
      <div className="mt-5 overflow-hidden rounded-box border border-line">
        <div className="hidden grid-cols-[minmax(0,1fr)_9rem_15rem] gap-4 border-b border-line bg-subtle px-5 py-2.5 text-[12px] font-medium text-muted lg:grid">
          <span>Repository</span>
          <span>Last push</span>
          <span>CI</span>
        </div>

        <ul className="list-none divide-y divide-line p-0">
          {visible.map((repo) => {
            const isChosen = repo.id === chosen;
            const python = repo.language === "Python";
            const blocked = repo.scan.state === "missing";
            return (
              <li key={repo.id} className={cn("relative", isChosen ? "bg-subtle" : "bg-surface")}>
                {isChosen && <span aria-hidden="true" className="absolute left-0 top-0 h-full w-[2px] bg-ink" />}
                <button
                  type="button"
                  onClick={() => setChosen(isChosen ? null : repo.id)}
                  aria-pressed={isChosen}
                  className="grid w-full grid-cols-1 items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-subtle lg:grid-cols-[minmax(0,1fr)_9rem_15rem] lg:gap-4"
                >
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-[14px] text-muted">
                        {repo.owner}/<span className="font-semibold text-ink">{repo.name}</span>
                      </span>
                      {repo.private && <Lock size={12} className="shrink-0 text-muted" />}
                    </span>
                    <span className="mt-1 block truncate text-[13px] text-body">{repo.description}</span>
                  </span>

                  <span className="text-[13px] text-muted">
                    {since(repo.pushedAt)}
                    <span className="mt-0.5 block">{repo.language}</span>
                  </span>

                  <span className="min-w-0">
                    <ScanCell scan={repo.scan} python={python} />
                  </span>
                </button>

                {/* No CI: show the exact thing to add, right here. */}
                {isChosen && blocked && (
                  <div className="border-t border-line bg-page px-5 py-6">
                    {python ? (
                      <>
                        <p className="text-[14px] font-semibold text-ink">Nothing to watch yet</p>
                        <p className="mt-1 text-[14px] text-body">
                          Add a workflow that runs your tests, push it, then scan again.
                        </p>
                        <p className="mt-5 font-mono text-[12px] text-muted">{WORKFLOW_PATH}</p>
                        <pre className="mt-2 overflow-x-auto rounded-box border border-line bg-code p-4 font-mono text-[12.5px] leading-relaxed text-body">
                          {WORKFLOW}
                        </pre>
                        <Button className="mt-5" onClick={() => rescan(repo)} disabled={rescanning === repo.id}>
                          <RefreshCw size={14} className={rescanning === repo.id ? "animate-spin" : undefined} />
                          {rescanning === repo.id ? "Reading workflows…" : "I've added it, scan again"}
                        </Button>
                      </>
                    ) : (
                      <p className="max-w-[46rem] text-[14px] leading-relaxed text-body">
                        This repository is {repo.language}. Phoenix fixes Python code that fails its tests in CI, and
                        there isn't any here. If this service has a Python backend in another repository, pick that
                        one instead.
                      </p>
                    )}
                  </div>
                )}
              </li>
            );
          })}

          {visible.length === 0 && (
            <li className="bg-surface px-5 py-14 text-center">
              <p className="text-[14.5px] text-body">No repository matches “{query}”.</p>
              <button
                type="button"
                onClick={() => setQuery("")}
                className="mt-2 text-[13px] font-medium text-ink hover:underline"
              >
                Clear the filter
              </button>
            </li>
          )}
        </ul>
      </div>

      {/* commit bar */}
      <div className="mt-6 flex flex-wrap items-center gap-4">
        <p className="text-[13px] text-muted">
          {!selected && "Select a repository to continue."}
          {selected && ready && (
            <>
              Watching{" "}
              <span className="font-medium text-ink">
                {selected.owner}/{selected.name}
              </span>{" "}
              · Phoenix steps in when a CI run fails
            </>
          )}
          {selected && !ready && selected.language === "Python" && (
            <span className="font-medium text-ink">Add a CI workflow to this repository first.</span>
          )}
          {selected && !ready && selected.language !== "Python" && (
            <span className="font-medium text-ink">Phoenix can only watch Python services.</span>
          )}
        </p>
        <Button tone="primary" size="lg" className="ml-auto" disabled={!ready} onClick={open}>
          Open the dashboard
          <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function Connect() {
  const { user, signIn } = useSession();
  return user ? <Picker /> : <SignIn onDone={signIn} />;
}
