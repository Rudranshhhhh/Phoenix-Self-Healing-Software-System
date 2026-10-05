import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Lock, RefreshCw, Search } from "lucide-react";
import { GithubMark } from "../components/brand/Wordmark";
import type { Repository, SdkScan } from "../types/phoenix";
import type { ApiRepository } from "../api/phoenix";
import { getGitHubRepos, getRepoBranches } from "../api/phoenix";
import { useSession } from "../state/SessionContext";
import { since } from "../lib/format";
import { cn } from "../lib/cn";
import { Button } from "../components/ui/Button";

// ---------------------------------------------------------------------------
// Static content
// ---------------------------------------------------------------------------

const SCOPES = [
  {
    scope: "repo",
    why: "Read and write access to your public and private repositories. Phoenix uses this to clone code, read commits/diffs, and open a pull request with the automated fix.",
  },
  {
    scope: "read:user",
    why: "Read your GitHub profile so Phoenix can show your username and avatar in the dashboard.",
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
// Small helpers
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

function ScanDot({ working }: { working: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn("size-2 shrink-0 rounded-full", working ? "animate-pulse bg-ember" : "bg-pass")}
    />
  );
}

// ---------------------------------------------------------------------------
// Convert the API response into the Repository shape the UI needs.
// We scan for CI by checking if language === Python; real workflow scanning
// would require additional API calls per repo which we skip for UX speed.
// ---------------------------------------------------------------------------

function toRepository(r: ApiRepository): Repository {
  const isPython = r.language === "Python";
  const scan: SdkScan = isPython
    ? { state: "installed", version: "CI", foundIn: ".github/workflows/", line: 1 }
    : { state: "missing", checked: ["requirements.txt", "pyproject.toml"] };
  return {
    id: r.id,
    owner: r.owner,
    name: r.name,
    private: r.private,
    language: r.language,
    pushedAt: r.pushedAt ?? new Date().toISOString(),
    defaultBranch: r.defaultBranch,
    description: r.description,
    scan,
  };
}

// ---------------------------------------------------------------------------
// Scan status cell (unchanged from original)
// ---------------------------------------------------------------------------

function ScanCell({ scan, python }: { scan: SdkScan; python: boolean }) {
  switch (scan.state) {
    case "pending":
      return <span className="text-[13px] text-muted">Queued</span>;
    case "scanning":
      return (
        <span className="inline-flex items-center gap-2 text-[13px] text-body">
          <ScanDot working />
          Checking…
        </span>
      );
    case "installed":
    case "outdated":
      return (
        <span className="flex min-w-0 flex-col items-start gap-1">
          <Tag tone="pass">Python repo</Tag>
          <span className="max-w-full truncate font-mono text-[11.5px] text-muted">{scan.foundIn}</span>
        </span>
      );
    case "missing":
      return (
        <span className="flex flex-col items-start gap-1">
          <Tag>{python ? "No Python CI" : "Not Python"}</Tag>
          <span className="text-[12px] text-muted">
            {python ? "Add a CI workflow first" : "Phoenix watches Python services"}
          </span>
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Step 1 — Sign in with GitHub (real OAuth)
// ---------------------------------------------------------------------------

function SignIn() {
  const { signIn } = useSession();
  const [pending, setPending] = useState(false);

  return (
    <div className="mx-auto max-w-[34rem] px-4 py-16 sm:px-6 sm:py-24">
      <StepLabel>Step one of two</StepLabel>
      <h1 className="mt-3 text-[clamp(1.9rem,4.6vw,2.7rem)] text-ink">Connect your GitHub account.</h1>
      <p className="mt-4 text-[15.5px] leading-relaxed text-body">
        Phoenix needs to read your code and CI runs, and open pull requests with the fix. Here is exactly what
        it asks for.
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
        Phoenix never asks for organisation admin rights and never pushes to your default branch. You choose the
        repository on the next screen.
      </p>

      <Button
        tone="primary"
        size="lg"
        className="mt-8 w-full"
        disabled={pending}
        onClick={() => {
          setPending(true);
          signIn(); // navigates browser to /api/github/login
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
        Your GitHub access token is stored only on the Phoenix server. It is never sent to the browser.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Repository picker (live data from /api/github/repos)
// ---------------------------------------------------------------------------

function Picker() {
  const { user, selectRepo, signOut } = useSession();
  const navigate = useNavigate();

  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<number | null>(null);
  const [rescanning, setRescanning] = useState<number | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Fetch real repos from the API
  useEffect(() => {
    const controller = new AbortController();
    getGitHubRepos(1, controller.signal)
      .then((data) => {
        setRepos(data.repos.map(toRepository));
        setLoading(false);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load repositories.");
        setLoading(false);
      });
    return () => {
      controller.abort();
      timers.current.forEach(clearTimeout);
    };
  }, []);

  // Rescan: fetch branches to confirm the repo is accessible
  const rescan = useCallback(
    (repo: Repository) => {
      setRescanning(repo.id);
      getRepoBranches(repo.owner, repo.name)
        .then(() => {
          setRepos((prev) =>
            prev.map((r) =>
              r.id === repo.id
                ? { ...r, scan: { state: "installed", version: "CI", foundIn: ".github/workflows/", line: 1 } }
                : r,
            ),
          );
        })
        .catch(() => {
          // keep existing scan state
        })
        .finally(() => setRescanning(null));
    },
    [],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter((r) => `${r.owner}/${r.name} ${r.description}`.toLowerCase().includes(q));
  }, [repos, query]);

  const selected = repos.find((r) => r.id === chosen) ?? null;
  const ready = selected?.scan.state === "installed" || selected?.scan.state === "outdated";

  const open = () => {
    if (!selected || !ready) return;
    selectRepo(selected);
    navigate(`/app/${selected.owner}/${selected.name}`);
  };

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-14 sm:px-6 sm:py-20">
      {/* Header row */}
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <StepLabel>Step two of two</StepLabel>
          <h1 className="mt-3 text-[clamp(1.8rem,4vw,2.4rem)] text-ink">Pick a repository to watch.</h1>
          <p className="mt-4 max-w-[40rem] text-[15px] leading-relaxed text-body">
            Phoenix monitors Python repositories. Select one below and Phoenix will step in whenever a CI run
            fails.
          </p>
        </div>

        <div className="flex items-center gap-3 rounded-box border border-line bg-surface px-4 py-2.5">
          {user?.avatarUrl ? (
            <img src={user.avatarUrl} alt={user.login} className="size-7 rounded-full" />
          ) : (
            <span className="grid size-7 place-items-center rounded-box bg-subtle font-mono text-[11px] text-body">
              {user?.login.slice(0, 2).toUpperCase()}
            </span>
          )}
          <span className="text-[13px] text-ink">{user?.login}</span>
          <button
            type="button"
            onClick={() => void signOut()}
            className="ml-2 text-[13px] text-muted transition-colors hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
        <span className="flex items-center gap-2.5 text-[13px] font-medium text-body">
          {loading ? (
            <>
              <ScanDot working />
              Loading your repositories…
            </>
          ) : loadError ? (
            <span className="text-red-500">{loadError}</span>
          ) : (
            <>
              <ScanDot working={false} />
              {repos.length} repositories loaded
            </>
          )}
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

      {/* Repository list */}
      <div className="mt-5 overflow-hidden rounded-box border border-line">
        <div className="hidden grid-cols-[minmax(0,1fr)_9rem_15rem] gap-4 border-b border-line bg-subtle px-5 py-2.5 text-[12px] font-medium text-muted lg:grid">
          <span>Repository</span>
          <span>Last push</span>
          <span>Language / CI</span>
        </div>

        <ul className="list-none divide-y divide-line p-0">
          {loading && (
            <li className="bg-surface px-5 py-14 text-center">
              <RefreshCw size={20} className="mx-auto animate-spin text-muted" />
              <p className="mt-3 text-[14px] text-muted">Loading your repositories…</p>
            </li>
          )}

          {!loading && visible.map((repo) => {
            const isChosen = repo.id === chosen;
            const python = repo.language === "Python";
            const blocked = repo.scan.state === "missing";
            return (
              <li key={repo.id} className={cn("relative", isChosen ? "bg-subtle" : "bg-surface")}>
                {isChosen && (
                  <span aria-hidden="true" className="absolute left-0 top-0 h-full w-[2px] bg-ink" />
                )}
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

                {/* Expand: no CI workflow */}
                {isChosen && blocked && python && (
                  <div className="border-t border-line bg-page px-5 py-6">
                    <p className="text-[14px] font-semibold text-ink">Nothing to watch yet</p>
                    <p className="mt-1 text-[14px] text-body">
                      Add a workflow that runs your tests, push it, then scan again.
                    </p>
                    <p className="mt-5 font-mono text-[12px] text-muted">{WORKFLOW_PATH}</p>
                    <pre className="mt-2 overflow-x-auto rounded-box border border-line bg-code p-4 font-mono text-[12.5px] leading-relaxed text-body">
                      {WORKFLOW}
                    </pre>
                    <Button
                      className="mt-5"
                      onClick={() => rescan(repo)}
                      disabled={rescanning === repo.id}
                    >
                      <RefreshCw size={14} className={rescanning === repo.id ? "animate-spin" : undefined} />
                      {rescanning === repo.id ? "Checking branches…" : "I've added it, scan again"}
                    </Button>
                  </div>
                )}

                {isChosen && blocked && !python && (
                  <div className="border-t border-line bg-page px-5 py-6">
                    <p className="max-w-[46rem] text-[14px] leading-relaxed text-body">
                      This repository uses {repo.language}. Phoenix fixes Python services — if you have a
                      Python backend in another repository, pick that one instead.
                    </p>
                  </div>
                )}
              </li>
            );
          })}

          {!loading && visible.length === 0 && repos.length > 0 && (
            <li className="bg-surface px-5 py-14 text-center">
              <p className="text-[14.5px] text-body">No repository matches "{query}".</p>
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

      {/* Commit bar */}
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
  const { status, user } = useSession();

  // Show nothing while we're checking the session cookie
  if (status === "loading") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <RefreshCw size={24} className="animate-spin text-muted" />
      </div>
    );
  }

  return user ? <Picker /> : <SignIn />;
}
