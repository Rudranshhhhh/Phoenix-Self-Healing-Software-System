import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Lock, RefreshCw, Search } from "lucide-react";
import { GithubMark } from "../components/brand/Wordmark";
import type { Repository, SdkScan } from "../types/phoenix";
import { MANIFESTS, repositoriesPending, scanResult } from "../mock/repos";
import { useSession } from "../state/SessionContext";
import { since } from "../lib/format";
import { cn } from "../lib/cn";
import { Button } from "../components/ui/Button";
import { Chip, Dot, Label, SectionRule } from "../components/ui/Primitives";
import { CodePane, CommandLine } from "../components/code/CodeSurface";
import type { Snippet } from "../components/code/CodeSurface";

// ---------------------------------------------------------------------------

const SCOPES = [
  {
    scope: "contents: read",
    why: "Clone the repositories you pick into a sandbox, so the agent can read the function in your traceback.",
  },
  {
    scope: "pull_requests: write",
    why: "Push a branch and open a pull request. Phoenix cannot merge one.",
  },
  {
    scope: "metadata: read",
    why: "List your repositories so you can choose which ones to watch.",
  },
];

const FIX_SNIPPET = (repo: Repository): Snippet[] => [
  {
    id: "add",
    tab: "Add to your entrypoint",
    filename: repo.name === "ledger-api" ? "wsgi.py" : "main.py",
    code: `import phoenix

phoenix.init(
    api_key="phx_live_xxxxxxxxxxxx",
    service="${repo.name}",
    repo="${repo.owner}/${repo.name}",
    release=phoenix.git_sha(),
)`,
  },
];

// ---------------------------------------------------------------------------
// Sign in
// ---------------------------------------------------------------------------

function SignIn({ onDone }: { onDone: () => void }) {
  const [pending, setPending] = useState(false);

  return (
    <div className="mx-auto max-w-[34rem] px-5 py-20 sm:px-8 sm:py-28">
      <SectionRule>Step one of two</SectionRule>
      <h1 className="mt-7 text-[clamp(1.9rem,4.6vw,2.7rem)]">Connect your GitHub account.</h1>
      <p className="mt-5 text-[15.5px] leading-relaxed text-bone-2">
        Phoenix needs to read the repository behind your traceback and open pull requests against it.
        Here is exactly what it asks for.
      </p>

      <ul className="mt-9 divide-y divide-ash-800 rounded-lg border border-ash-800 bg-ash-900">
        {SCOPES.map((s) => (
          <li key={s.scope} className="p-5">
            <code className="font-mono text-[12.5px] text-sodium">{s.scope}</code>
            <p className="mt-2 text-[14px] leading-relaxed text-bone-2">{s.why}</p>
          </li>
        ))}
      </ul>

      <p className="mt-5 text-[13.5px] leading-relaxed text-bone-3">
        It never asks for organization admin, and never asks for permission to push to your default
        branch. You choose the repositories on the next screen.
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

      <p className="mt-4 text-center font-mono text-[11px] text-bone-4">
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
      return <span className="font-mono text-[11.5px] text-bone-4">queued</span>;
    case "scanning":
      return (
        <span className="inline-flex items-center gap-2 font-mono text-[11.5px] text-bone-2">
          <Dot tone="working" pulse />
          reading manifests
          <span className="animate-caret text-sodium">▌</span>
        </span>
      );
    case "installed":
      return (
        <span className="flex flex-col items-start gap-1.5">
          <Chip tone="jade">phoenix-sdk {scan.version}</Chip>
          <span className="font-mono text-[11px] text-bone-4">
            {scan.foundIn}:{scan.line}
          </span>
        </span>
      );
    case "outdated":
      return (
        <span className="flex flex-col items-start gap-1.5">
          <Chip tone="sodium">
            {scan.version} → {scan.latest}
          </Chip>
          <span className="font-mono text-[11px] text-bone-4">
            {scan.foundIn}:{scan.line} · upgrade when you can
          </span>
        </span>
      );
    case "missing":
      return (
        <span className="flex flex-col items-start gap-1.5">
          <Chip tone="brick">{python ? "not installed" : "not a python service"}</Chip>
          <span className="font-mono text-[11px] text-bone-4">
            {python ? `checked ${scan.checked.length} manifests` : "no python entrypoint"}
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

  // Walk the list, one repository at a time — the scan is the moment on this page.
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
      // Simulates the developer having added the three lines and pushed.
      patch(repo.id, { state: "installed", version: "0.4.2", foundIn: "requirements.txt", line: 9 });
      setRescanning(null);
    }, 1100);
  };

  const open = () => {
    if (!selected || !ready) return;
    selectRepo(selected);
    navigate(`/app/${selected.owner}/${selected.name}`);
  };

  return (
    <div className="mx-auto max-w-[1180px] px-5 py-16 sm:px-8 sm:py-20">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <SectionRule>Step two of two</SectionRule>
          <h1 className="mt-6 text-[clamp(1.8rem,4vw,2.4rem)]">Pick a repository to watch.</h1>
          <p className="mt-4 max-w-[40rem] text-[15px] leading-relaxed text-bone-2">
            Phoenix reads each repository's dependency manifests — {MANIFESTS.join(", ")} — looking for{" "}
            <code className="font-mono text-[13.5px] text-bone">phoenix-sdk</code>. A repository without it
            cannot report anything yet.
          </p>
        </div>

        <div className="flex items-center gap-3 rounded-md border border-ash-800 bg-ash-900 px-4 py-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-xs bg-ash-800 font-mono text-[11px] text-bone-2">
            {user?.login.slice(0, 2).toUpperCase()}
          </span>
          <span className="font-mono text-[12px] text-bone-2">{user?.login}</span>
          <button
            onClick={signOut}
            className="ml-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-bone-4 transition-colors hover:text-brick"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* scan progress + search */}
      <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
        <span className="flex items-center gap-2.5">
          <Dot tone={scanning ? "working" : "healthy"} pulse={scanning} />
          <Label className={scanning ? "text-iris" : "text-jade"}>
            {scanning ? `Scanning ${done}/${repos.length}` : `${repos.length} repositories scanned`}
          </Label>
        </span>

        <div className="relative ml-auto w-full sm:w-72">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-bone-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter repositories"
            aria-label="Filter repositories"
            className="h-10 w-full rounded-sm border border-ash-800 bg-ash-900 pl-9 pr-3 font-mono text-[12.5px] text-bone placeholder:text-bone-4 focus:border-ash-600 focus:outline-none"
          />
        </div>
      </div>

      {/* the list */}
      <div className="mt-5 overflow-hidden rounded-lg border border-ash-800">
        <div className="hidden grid-cols-[minmax(0,1fr)_9rem_13rem] gap-4 border-b border-ash-800 bg-ash-925 px-5 py-2.5 lg:grid">
          <Label>Repository</Label>
          <Label>Last push</Label>
          <Label>phoenix-sdk</Label>
        </div>

        <ul className="divide-y divide-ash-800">
          {visible.map((repo) => {
            const isChosen = repo.id === chosen;
            const python = repo.language === "Python";
            const blocked = repo.scan.state === "missing";
            return (
              <li key={repo.id} className={cn("bg-ash-900 transition-colors", isChosen && "bg-ash-850")}>
                <button
                  type="button"
                  onClick={() => setChosen(isChosen ? null : repo.id)}
                  aria-pressed={isChosen}
                  className="grid w-full grid-cols-1 items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-ash-850 lg:grid-cols-[minmax(0,1fr)_9rem_13rem] lg:gap-4"
                >
                  <span
                    className={cn(
                      "absolute left-0 h-full w-[2px] transition-colors",
                      isChosen ? "bg-sodium" : "bg-transparent",
                    )}
                    style={{ position: "absolute" }}
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="truncate font-mono text-[13.5px] text-bone-3">
                        {repo.owner}/<span className="font-medium text-bone">{repo.name}</span>
                      </span>
                      {repo.private && <Lock size={11} className="shrink-0 text-bone-4" />}
                    </span>
                    <span className="mt-1 block truncate text-[13px] text-bone-3">{repo.description}</span>
                  </span>

                  <span className="font-mono text-[11.5px] text-bone-3">
                    {since(repo.pushedAt)}
                    <span className="mt-1 block text-bone-4">{repo.language}</span>
                  </span>

                  <span>
                    <ScanCell scan={repo.scan} python={python} />
                  </span>
                </button>

                {/* Missing SDK: show the exact thing to add, right here. */}
                {isChosen && blocked && (
                  <div className="border-t border-ash-800 bg-ash-925 px-5 py-6">
                    {python ? (
                      <>
                        <div className="flex flex-wrap items-center gap-3">
                          <Label className="text-brick">Nothing to report from yet</Label>
                          <span className="text-[13.5px] text-bone-3">
                            Add the package and the init call, push, then scan again.
                          </span>
                        </div>
                        <div className="mt-5 space-y-4">
                          <CommandLine command="pip install phoenix-sdk" />
                          <CodePane snippets={FIX_SNIPPET(repo)} />
                        </div>
                        <Button
                          className="mt-5"
                          onClick={() => rescan(repo)}
                          disabled={rescanning === repo.id}
                        >
                          <RefreshCw
                            size={14}
                            className={rescanning === repo.id ? "animate-spin" : undefined}
                          />
                          {rescanning === repo.id ? "Reading manifests…" : "I've added it — scan again"}
                        </Button>
                      </>
                    ) : (
                      <p className="max-w-[46rem] text-[14px] leading-relaxed text-bone-3">
                        This repository is {repo.language}. The reporter wraps a Python WSGI, ASGI or Celery
                        entrypoint, and there isn't one here. If this service has a Python sidecar, connect
                        that repository instead.
                      </p>
                    )}
                  </div>
                )}
              </li>
            );
          })}

          {visible.length === 0 && (
            <li className="bg-ash-900 px-5 py-14 text-center">
              <p className="text-[14.5px] text-bone-2">No repository matches “{query}”.</p>
              <button
                onClick={() => setQuery("")}
                className="mt-2 font-mono text-[11.5px] uppercase tracking-[0.12em] text-sodium hover:underline"
              >
                Clear the filter
              </button>
            </li>
          )}
        </ul>
      </div>

      {/* commit bar */}
      <div className="mt-6 flex flex-wrap items-center gap-4">
        <p className="font-mono text-[11.5px] text-bone-3">
          {!selected && "Select a repository to continue."}
          {selected && ready && (
            <>
              Watching{" "}
              <span className="text-bone">
                {selected.owner}/{selected.name}
              </span>{" "}
              · reports arrive as soon as it throws
            </>
          )}
          {selected && !ready && selected.language === "Python" && (
            <span className="text-brick">Install phoenix-sdk in this repository first.</span>
          )}
          {selected && !ready && selected.language !== "Python" && (
            <span className="text-brick">Phoenix can only watch Python services.</span>
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
