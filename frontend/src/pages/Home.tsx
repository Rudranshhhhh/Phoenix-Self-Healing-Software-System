import { ArrowRight } from "lucide-react";
import { GithubMark } from "../components/brand/Wordmark";
import { HealingTraceback } from "../components/signature/HealingTraceback";
import { CodePane, CommandLine } from "../components/code/CodeSurface";
import type { Snippet } from "../components/code/CodeSurface";
import { ButtonLink } from "../components/ui/Button";
import { Chip, Label, SectionRule } from "../components/ui/Primitives";
import { Reveal } from "../components/ui/Reveal";
import { HERO_INCIDENT } from "../mock/incidents";

// ---------------------------------------------------------------------------

const SNIPPETS: Snippet[] = [
  {
    id: "fastapi",
    tab: "FastAPI",
    filename: "main.py",
    code: `from fastapi import FastAPI
import phoenix

app = FastAPI()

phoenix.init(
    api_key="phx_live_xxxxxxxxxxxx",   # copy this from your dashboard
    service="checkout-api",
    repo="your-org/orbital-checkout",
    release=phoenix.git_sha(),
)

app.add_middleware(phoenix.ASGIReporter)`,
  },
  {
    id: "flask",
    tab: "Flask",
    filename: "wsgi.py",
    code: `from flask import Flask
import phoenix

app = Flask(__name__)

phoenix.init(
    api_key="phx_live_xxxxxxxxxxxx",
    service="ledger-api",
    repo="your-org/ledger-api",
)

app.wsgi_app = phoenix.WSGIReporter(app.wsgi_app)`,
  },
  {
    id: "celery",
    tab: "Celery",
    filename: "worker.py",
    code: `from celery import Celery
import phoenix

phoenix.init(api_key="phx_live_xxxxxxxxxxxx", service="invoice-worker")

app = Celery("invoice-worker", broker="redis://localhost:6379/0")
phoenix.watch_celery(app)


@app.task
@phoenix.watch          # report timings for one hot task
def render_pdf(invoice_id: str) -> None:
    ...`,
  },
  {
    id: "script",
    tab: "Any script",
    filename: "nightly_sync.py",
    code: `import phoenix

phoenix.init(api_key="phx_live_xxxxxxxxxxxx", service="nightly-sync")

# Anything raised inside the block is reported with its full frame.
with phoenix.report():
    run_reconciliation()`,
  },
];

const STAGES = [
  {
    role: "In your app",
    name: "phoenix-sdk",
    body: "Wraps your WSGI or ASGI app and your Celery workers. When something raises, it packages the exception, every stack frame with its source line, the request that triggered it, and the sixty seconds of CPU and memory that led up to it.",
    artifact: "report.json  →",
  },
  {
    role: "In Phoenix",
    name: "the service you are looking at",
    body: "Collapses identical failures into one incident, counts how many people hit it, and keeps your live process metrics on screen. This is where you decide whether a failure is worth repairing — nothing moves until you say so.",
    artifact: "incident  →",
  },
  {
    role: "In your repo",
    name: "the code agent",
    body: "Clones your repository at the failing commit into a throwaway sandbox, reproduces the traceback, writes the smallest patch that makes it stop, runs your whole test suite, and opens a pull request that links back to the incident.",
    artifact: "pull request",
  },
];

const LIMITS = [
  {
    heading: "It does not push to your default branch.",
    body: "Every repair arrives as a pull request on its own branch, with the incident, the traceback and the test output in the description.",
  },
  {
    heading: "It does not touch your running processes.",
    body: "Phoenix never restarts, scales, redeploys or kills anything. It reads and it reports. Your deploy pipeline stays the only thing that ships code.",
  },
  {
    heading: "It does not read repositories you did not pick.",
    body: "GitHub access is scoped to the repositories you select on the connect screen, and you can drop one at any time.",
  },
  {
    heading: "It does not guess quietly.",
    body: "If the agent cannot reproduce the failure in a sandbox, or the patch breaks a test, the incident is marked unfixable with the reason and left for you.",
  },
];

// ---------------------------------------------------------------------------

export default function Home() {
  return (
    <>
      {/* ================= hero ================= */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="ledger-ground absolute inset-0 animate-drift" />
        <div aria-hidden className="lamp absolute inset-x-0 -top-24 h-[520px]" />

        <div className="relative mx-auto max-w-[1180px] px-5 pb-16 pt-16 sm:px-8 sm:pt-24">
          <div className="enter max-w-[54rem]" style={{ animationDelay: "40ms" }}>
            <Label className="text-sodium/80">Self-healing for Python services</Label>
            <h1
              className="mt-5 text-[clamp(2.5rem,7.2vw,4.6rem)]"
              style={{ fontVariationSettings: '"wdth" 86', fontWeight: 500 }}
            >
              Phoenix turns a traceback
              <br />
              into a pull request.
            </h1>
          </div>

          <p
            className="enter mt-7 max-w-[44rem] text-[17px] leading-[1.65] text-bone-2 sm:text-[18px]"
            style={{ animationDelay: "160ms" }}
          >
            Install one package. When your service throws, Phoenix captures the frame with its request
            context and the metrics around it, reproduces the failure against your repository, writes the
            smallest patch it can, runs your test suite, and opens a pull request. You review it the way you
            review everything else.
          </p>

          <div className="enter mt-9 flex flex-wrap items-center gap-3" style={{ animationDelay: "260ms" }}>
            <ButtonLink to="/connect" tone="primary" size="lg">
              <GithubMark size={16} />
              Connect a repository
            </ButtonLink>
            <a
              href="#install"
              className="inline-flex h-12 items-center gap-2 rounded-sm border border-ash-700 bg-ash-850 px-5 font-mono text-[13px] text-bone-2 transition-colors hover:border-ash-600 hover:text-bone"
            >
              pip install phoenix-sdk
            </a>
          </div>

          <p className="enter mt-5 font-mono text-[11.5px] text-bone-4" style={{ animationDelay: "320ms" }}>
            Python 3.9+ · FastAPI, Flask, Django, Celery, or any process you can wrap
          </p>

          {/* the signature: a captured failure, healing itself */}
          <div className="enter mt-14 sm:mt-16" style={{ animationDelay: "420ms" }}>
            <div className="mb-3 flex items-end justify-between gap-4">
              <Label>One incident, start to finish</Label>
              <Label className="hidden text-bone-4 sm:inline">Live from the demo workspace</Label>
            </div>
            <HealingTraceback incident={HERO_INCIDENT} />
          </div>
        </div>
      </section>

      {/* ================= how it works ================= */}
      <section id="how" className="mx-auto max-w-[1180px] scroll-mt-20 px-5 py-24 sm:px-8 sm:py-28">
        <Reveal>
          <SectionRule>Three parts, one handoff</SectionRule>
          <h2 className="mt-7 max-w-[36rem] text-[clamp(1.85rem,3.6vw,2.6rem)]">
            You install one of them. We run the other two.
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-px overflow-hidden rounded-lg border border-ash-800 bg-ash-800 md:grid-cols-3">
          {STAGES.map((stage, i) => (
            <Reveal key={stage.name} delay={i * 110}>
              <article className="flex h-full flex-col bg-ash-900 p-6 transition-colors hover:bg-ash-850 sm:p-7">
                <Label className="text-sodium/75">{stage.role}</Label>
                <h3 className="mt-4 font-mono text-[15px] font-medium tracking-tight text-bone">
                  {stage.name}
                </h3>
                <p className="mt-4 flex-1 text-[14.5px] leading-relaxed text-bone-2">{stage.body}</p>
                <div className="mt-7 flex items-center gap-2 border-t border-ash-800 pt-4">
                  <span className="font-mono text-[11.5px] tracking-tight text-bone-3">
                    {stage.artifact}
                  </span>
                </div>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal delay={120}>
          <p className="mt-6 max-w-[42rem] text-[14px] text-bone-3">
            The only thing that ever leaves your process is the report: the exception, the frames, the
            request line, and the metric window. Phoenix reads your source in a sandbox from your own
            repository, not from your running server.
          </p>
        </Reveal>
      </section>

      {/* ================= install ================= */}
      <section id="install" className="relative scroll-mt-20 border-y border-ash-800 bg-ash-925">
        <div className="mx-auto max-w-[1180px] px-5 py-24 sm:px-8 sm:py-28">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-16">
            <Reveal>
              <SectionRule>Install</SectionRule>
              <h2 className="mt-7 text-[clamp(1.85rem,3.6vw,2.5rem)]">
                Three lines in your entrypoint.
              </h2>
              <p className="mt-5 text-[15px] leading-relaxed text-bone-2">
                Add the package, call <code className="font-mono text-[13.5px] text-bone">init</code> once
                with your service name and repository, and wrap the app. That is the whole integration.
              </p>
              <p className="mt-5 text-[14px] leading-relaxed text-bone-3">
                The key below is a placeholder. Your real one appears on the dashboard the moment you
                connect a repository, and it is scoped to that repository alone.
              </p>
              <div className="mt-7 flex flex-wrap gap-2">
                <Chip>py 3.9 – 3.13</Chip>
                <Chip>no agent process</Chip>
                <Chip>~4 kb per report</Chip>
              </div>
            </Reveal>

            <Reveal delay={110} className="min-w-0">
              <div className="space-y-4">
                <CommandLine command="pip install phoenix-sdk" />
                <CodePane snippets={SNIPPETS} />
              </div>
              <p className="mt-4 font-mono text-[11.5px] leading-relaxed text-bone-4">
                Sample integration for the walkthrough. Swap in your own service name, repository and key.
              </p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ================= limits ================= */}
      <section id="limits" className="mx-auto max-w-[1180px] scroll-mt-20 px-5 py-24 sm:px-8 sm:py-28">
        <Reveal>
          <SectionRule>Limits</SectionRule>
          <h2 className="mt-7 max-w-[34rem] text-[clamp(1.85rem,3.6vw,2.6rem)]">
            Four things Phoenix will not do.
          </h2>
          <p className="mt-5 max-w-[38rem] text-[15px] leading-relaxed text-bone-2">
            An agent with write access to your repository should be boring and predictable. These are the
            lines it does not cross.
          </p>
        </Reveal>

        <ul className="mt-12 divide-y divide-ash-800 border-y border-ash-800">
          {LIMITS.map((limit, i) => (
            <Reveal key={limit.heading} as="li" delay={i * 80}>
              <div className="grid gap-2 py-6 sm:grid-cols-[2.5rem_minmax(0,22rem)_minmax(0,1fr)] sm:gap-6">
                <span aria-hidden className="hidden font-mono text-[15px] text-brick/70 sm:block">
                  −
                </span>
                <h3 className="font-sans text-[15.5px] font-medium leading-snug tracking-normal text-bone">
                  {limit.heading}
                </h3>
                <p className="text-[14.5px] leading-relaxed text-bone-3">{limit.body}</p>
              </div>
            </Reveal>
          ))}
        </ul>
      </section>

      {/* ================= closing ================= */}
      <section className="relative overflow-hidden border-t border-ash-800">
        <div aria-hidden className="lamp absolute inset-x-0 bottom-0 h-[360px] rotate-180" />
        <div className="relative mx-auto max-w-[1180px] px-5 py-24 text-center sm:px-8 sm:py-28">
          <Reveal>
            <h2 className="mx-auto max-w-[30rem] text-[clamp(1.9rem,4vw,2.8rem)]">
              Point it at one repository and wait for something to break.
            </h2>
            <p className="mx-auto mt-6 max-w-[34rem] text-[15.5px] leading-relaxed text-bone-2">
              Phoenix checks whether the SDK is already in your dependency manifest, so you will know
              straight away whether there is anything left to install.
            </p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <ButtonLink to="/connect" tone="primary" size="lg">
                Connect a repository
                <ArrowRight size={16} />
              </ButtonLink>
              <ButtonLink to="/app" tone="quiet" size="lg">
                See the live dashboard
              </ButtonLink>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
