import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { GithubMark } from "../components/brand/Wordmark";
import { ButtonLink } from "../components/ui/Button";
import { HealReplay } from "../components/home/HealReplay";
import { LiveHero } from "../components/incidents/LiveHero";
import { PipelineArc } from "../components/phoenix/PipelineArc";
import { useIncident, useIncidentList } from "../hooks/useIncidentList";
import { isActive } from "../lib/incident";
import { SHOW_REJECTED } from "../lib/flags";
import { REPO } from "../lib/repo";

const HERO_FRESH_MS = 10 * 60 * 1000;

const STAGES = [
  {
    name: "Detected",
    body: "A CI run fails on your branch. Phoenix opens an incident with the traceback and the commit that broke it.",
  },
  {
    name: "Diagnosing",
    body: "It reads the stack and your code, and names the file and line it blames, with how sure it is.",
  },
  {
    name: "Fix proposed",
    body: "It writes the smallest change that should stop the failure. Nothing touches your repository yet.",
  },
  {
    name: "Validating",
    body: "The patch runs against your test suite in a throwaway Docker sandbox.",
  },
  {
    name: "Validated",
    body: "Every test passed in the sandbox. The fix is ready for a pull request.",
  },
  {
    name: "PR opened",
    body: "Phoenix pushes a phoenix/fix branch and opens a pull request that links back to the incident.",
  },
];

const LIMITS = [
  {
    heading: "It does not push to your default branch.",
    body: "Every fix arrives as a pull request on its own phoenix/fix branch, with the incident, the traceback and the test output.",
  },
  {
    heading: "It does not merge anything.",
    body: "A person reviews the pull request and decides. Phoenix cannot merge it.",
  },
  {
    heading: "It does not touch your running services.",
    body: "It works from your repository and your CI logs, inside a sandbox. It never restarts, redeploys or changes production.",
  },
  {
    heading: "It does not guess quietly.",
    body: "If the patch fails a test, the incident is marked rejected with the reason, no pull request is opened, and it is left for you.",
  },
];

/** The live incident from the demo API, the same view as the dashboard hero. */
function LiveDemo() {
  const { incidents, loading, error } = useIncidentList();
  const visible = useMemo(
    () => (SHOW_REJECTED ? incidents : incidents.filter((i) => i.status !== "rejected")),
    [incidents],
  );
  const hero = useMemo(() => {
    const now = Date.now();
    const live = visible.find(
      (i) => isActive(i.status) && now - new Date(i.updated_at).getTime() < HERO_FRESH_MS,
    );
    return live ?? visible[0] ?? null;
  }, [visible]);
  const detail = useIncident(hero?.id ?? null).incident;
  const repo = { name: REPO.name, branch: REPO.branch };

  if (loading) return <PipelineArc status={null} repo={repo} />;

  if (error && incidents.length === 0) {
    return (
      <>
        <PipelineArc status={null} repo={repo} />
        <p className="pb-4 text-center text-[14px] text-muted">
          The live demo is offline. Start phoenix-api on port 8000 to see Phoenix at work.
        </p>
      </>
    );
  }

  return (
    <LiveHero
      summary={hero}
      incident={detail && hero && detail.id === hero.id ? detail : null}
      branch={REPO.branch}
      repoName={REPO.name}
    />
  );
}

export default function Home() {
  return (
    <>
      {/* ================= hero ================= */}
      <section className="mx-auto max-w-[1200px] px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <div className="max-w-[54rem]">
          <p className="text-[14px] font-medium text-muted">Self-healing for Python services</p>
          <h1
            className="mt-4 text-[clamp(2.4rem,6.4vw,4.2rem)] text-ink"
            style={{ fontVariationSettings: '"wdth" 86' }}
          >
            Phoenix turns a failing CI run
            <br className="hidden sm:inline" /> into a pull request.
          </h1>
        </div>

        <p className="mt-6 max-w-[44rem] text-[17px] leading-[1.65] text-body">
          When a test fails on your branch, Phoenix reads the traceback, finds the root cause, writes the
          smallest patch it can and tests it in a Docker sandbox. If the tests pass, it opens a pull request.
          You review it the way you review everything else.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <ButtonLink to="/connect" tone="primary" size="lg">
            <GithubMark size={16} />
            Connect a repository
          </ButtonLink>
          <ButtonLink to="/app" size="lg">
            See the live dashboard
          </ButtonLink>
        </div>

        <p className="mt-5 text-[13px] text-muted">Python services · GitHub Actions · Docker sandbox</p>

        {/* the live demo incident */}
        <div className="mt-12 sm:mt-14">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span className="text-[13px] font-medium text-muted">Live from the demo workspace</span>
            <Link
              to="/app"
              className="inline-flex items-center gap-1 text-[13px] font-medium text-ink no-underline hover:underline"
            >
              All incidents
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="rounded-box border border-line bg-surface px-4 pt-4 sm:px-6">
            <LiveDemo />
          </div>
        </div>
      </section>

      <HealReplay />

      {/* ================= how it works ================= */}
      <section id="how" className="scroll-mt-24 border-t border-line">
        <div className="mx-auto max-w-[1200px] px-4 py-20 sm:px-6 sm:py-24">
          <p className="text-[14px] font-medium text-muted">How it works</p>
          <h2 className="mt-3 max-w-[36rem] text-[clamp(1.85rem,3.6vw,2.6rem)] text-ink">
            From a red build to a reviewed fix.
          </h2>
          <p className="mt-4 max-w-[40rem] text-[15px] leading-relaxed text-body">
            Every incident moves through the same six stages. The dashboard shows where each one is, live.
          </p>

          <ol className="mt-10 grid list-none gap-px overflow-hidden rounded-box border border-line bg-line p-0 sm:grid-cols-2 lg:grid-cols-3">
            {STAGES.map((stage, i) => (
              <li key={stage.name} className="flex flex-col bg-surface p-5 sm:p-6">
                <span className="font-mono text-[12px] tabular-nums text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-3 font-sans text-[16px] font-semibold leading-snug tracking-normal text-ink">
                  {stage.name}
                </h3>
                <p className="mt-2 text-[14px] leading-relaxed text-body">{stage.body}</p>
              </li>
            ))}
          </ol>

          <p className="mt-5 max-w-[42rem] text-[14px] leading-relaxed text-muted">
            If the patch fails a test, the incident stops at Validating and is marked rejected, with the reason.
            No pull request is opened.
          </p>
        </div>
      </section>

      {/* ================= limits ================= */}
      <section id="limits" className="scroll-mt-24 border-t border-line">
        <div className="mx-auto max-w-[1200px] px-4 py-20 sm:px-6 sm:py-24">
          <p className="text-[14px] font-medium text-muted">Limits</p>
          <h2 className="mt-3 max-w-[34rem] text-[clamp(1.85rem,3.6vw,2.6rem)] text-ink">
            Four things Phoenix will not do.
          </h2>
          <p className="mt-4 max-w-[38rem] text-[15px] leading-relaxed text-body">
            An agent that writes to your repository should be boring and predictable. These are the lines it
            does not cross.
          </p>

          <ul className="mt-10 list-none divide-y divide-line border-y border-line p-0">
            {LIMITS.map((limit) => (
              <li
                key={limit.heading}
                className="grid gap-2 py-5 sm:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] sm:gap-6"
              >
                <h3 className="font-sans text-[15.5px] font-semibold leading-snug tracking-normal text-ink">
                  {limit.heading}
                </h3>
                <p className="text-[14.5px] leading-relaxed text-body">{limit.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ================= closing ================= */}
      <section className="border-t border-line">
        <div className="mx-auto max-w-[1200px] px-4 py-20 text-center sm:px-6 sm:py-24">
          <h2 className="mx-auto max-w-[30rem] text-[clamp(1.9rem,4vw,2.8rem)] text-ink">
            Point it at one repository and wait for a build to break.
          </h2>
          <p className="mx-auto mt-5 max-w-[34rem] text-[15.5px] leading-relaxed text-body">
            Connect GitHub, pick a repository, and Phoenix starts watching its CI runs.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <ButtonLink to="/connect" tone="primary" size="lg">
              Connect a repository
              <ArrowRight size={16} />
            </ButtonLink>
            <ButtonLink to="/app" size="lg">
              See the live dashboard
            </ButtonLink>
          </div>
        </div>
      </section>
    </>
  );
}
