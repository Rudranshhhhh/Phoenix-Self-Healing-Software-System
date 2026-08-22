// ---------------------------------------------------------------------------
// A stand-in for the SDK's live report stream.
//
// The real thing is a socket.io feed of `sample` and `incident` events from the
// Phoenix backend. This produces the same shapes on the same 1.5s cadence so
// that swapping in the socket means replacing `subscribe` and nothing else.
// ---------------------------------------------------------------------------

import type { FeedEntry, Incident, Sample, ServiceProcess } from "../types/phoenix";
import { MOCK_INCIDENTS } from "./incidents";

export const TICK_MS = 1500;
const WINDOW = 64; // samples kept per service ≈ 96 seconds

export type FaultKind = "memory_leak" | "cpu_spike" | "slow_dependency" | "exception_burst";

export const FAULTS: Array<{ kind: FaultKind; label: string; hint: string }> = [
  { kind: "exception_burst", label: "Unhandled exception", hint: "Raises a TypeError on the checkout path" },
  { kind: "memory_leak", label: "Memory leak", hint: "Leaks ~1.5% of the process limit per sample" },
  { kind: "cpu_spike", label: "CPU saturation", hint: "Pins the web worker near one full core" },
  { kind: "slow_dependency", label: "Slow dependency", hint: "Adds 400ms to every database round trip" },
];

interface Baseline {
  cpu: number;
  memory: number;
  rpm: number;
  p95: number;
  errorRate: number;
}

interface Sim {
  process: ServiceProcess;
  base: Baseline;
  drift: number; // accumulated memory leak, in percent
  faults: Set<FaultKind>;
}

export interface EngineState {
  services: ServiceProcess[];
  incidents: Incident[];
  feed: FeedEntry[];
  activeFaults: FaultKind[];
}

type Listener = (state: EngineState) => void;

// -- deterministic-ish noise --------------------------------------------------

function noise(spread: number): number {
  return (Math.random() - 0.5) * spread;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

// ---------------------------------------------------------------------------

const SEEDS: Array<{ p: Omit<ServiceProcess, "history">; base: Baseline }> = [
  {
    p: {
      id: "web",
      name: "checkout-api",
      role: "web",
      runtime: "uvicorn 0.34 · py3.12",
      status: "healthy",
      pid: 1184,
      uptimeSeconds: 412_800,
      memoryLimitMb: 1024,
    },
    base: { cpu: 22, memory: 46, rpm: 1840, p95: 118, errorRate: 0.2 },
  },
  {
    p: {
      id: "worker",
      name: "invoice-worker",
      role: "worker",
      runtime: "celery 5.4 · py3.12",
      status: "healthy",
      pid: 1211,
      uptimeSeconds: 412_760,
      memoryLimitMb: 512,
    },
    base: { cpu: 14, memory: 38, rpm: 240, p95: 640, errorRate: 0.0 },
  },
  {
    p: {
      id: "scheduler",
      name: "cron-scheduler",
      role: "scheduler",
      runtime: "apscheduler 3.10 · py3.12",
      status: "healthy",
      pid: 1233,
      uptimeSeconds: 412_740,
      memoryLimitMb: 256,
    },
    base: { cpu: 3, memory: 19, rpm: 12, p95: 44, errorRate: 0.0 },
  },
];

const BOOT_FEED: Array<Omit<FeedEntry, "id" | "t">> = [
  { kind: "info", source: "phoenix-sdk", text: "reporter attached · 3 processes registered" },
  { kind: "info", source: "checkout-api", text: "release 9c41ab7 · 214 tests green at build time" },
  { kind: "warn", source: "checkout-api", text: "PHX-2288 KeyError 'shipping_address' · 23 events" },
  { kind: "repair", source: "code-agent", text: "PHX-2284 pull request #482 opened on phoenix/fix-invoice-legal-name" },
  { kind: "error", source: "checkout-api", text: "PHX-2291 TypeError in price_after_discount · patch awaiting review" },
];

class TelemetryEngine {
  private sims: Sim[];
  private incidents: Incident[] = [...MOCK_INCIDENTS];
  private feed: FeedEntry[];
  private listeners = new Set<Listener>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private seq = 0;

  constructor() {
    const now = Date.now();
    this.sims = SEEDS.map(({ p, base }) => ({
      process: {
        ...p,
        history: Array.from({ length: WINDOW }, (_, i) =>
          this.synth(base, 0, new Set(), now - (WINDOW - i) * TICK_MS),
        ),
      },
      base,
      drift: 0,
      faults: new Set<FaultKind>(),
    }));
    this.feed = BOOT_FEED.map((e, i) => ({ ...e, id: `boot-${i}`, t: now - (BOOT_FEED.length - i) * 9_000 }));
  }

  private synth(base: Baseline, drift: number, faults: Set<FaultKind>, t: number): Sample {
    const cpu = clamp(base.cpu + noise(6) + (faults.has("cpu_spike") ? 68 : 0), 0.4, 99.8);
    const memory = clamp(base.memory + noise(2.4) + drift, 2, 99.6);
    const rpm = Math.max(0, base.rpm + noise(base.rpm * 0.14));
    const p95 = Math.max(
      8,
      base.p95 +
        noise(base.p95 * 0.22) +
        (faults.has("slow_dependency") ? 400 : 0) +
        (faults.has("cpu_spike") ? 260 : 0),
    );
    const errorRate = clamp(
      base.errorRate + Math.abs(noise(0.3)) + (faults.has("exception_burst") ? 7.4 + noise(2) : 0),
      0,
      100,
    );
    return { t, cpu, memory, memoryMb: 0, rpm, p95, errorRate };
  }

  private statusOf(sim: Sim, s: Sample): ServiceProcess["status"] {
    if (s.memory > 92 || s.errorRate > 5) return "failing";
    if (s.cpu > 80 || s.memory > 78 || s.p95 > sim.base.p95 * 2.5 || s.errorRate > 1) return "degraded";
    return "healthy";
  }

  private tick = () => {
    const now = Date.now();
    for (const sim of this.sims) {
      if (sim.faults.has("memory_leak")) sim.drift = Math.min(52, sim.drift + 1.5);
      const sample = this.synth(sim.base, sim.drift, sim.faults, now);
      sample.memoryMb = Math.round((sample.memory / 100) * sim.process.memoryLimitMb);
      sim.process.history = [...sim.process.history.slice(-(WINDOW - 1)), sample];
      sim.process.status = this.statusOf(sim, sample);
      sim.process.uptimeSeconds += TICK_MS / 1000;
    }
    this.emit();
  };

  private push(entry: Omit<FeedEntry, "id" | "t">) {
    this.seq += 1;
    this.feed = [...this.feed.slice(-120), { ...entry, id: `e-${this.seq}`, t: Date.now() }];
  }

  private emit() {
    const state = this.state();
    for (const listener of this.listeners) listener(state);
  }

  state(): EngineState {
    const active = new Set<FaultKind>();
    for (const sim of this.sims) for (const f of sim.faults) active.add(f);
    return {
      services: this.sims.map((s) => ({ ...s.process })),
      incidents: [...this.incidents],
      feed: [...this.feed],
      activeFaults: [...active],
    };
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    if (!this.timer) this.timer = setInterval(this.tick, TICK_MS);
    listener(this.state());
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0 && this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    };
  }

  // -- demo controls ---------------------------------------------------------

  /** Inject a fault into the web process, the way the failure panel does. */
  inject(kind: FaultKind) {
    const target = this.sims[0];
    if (target.faults.has(kind)) return;
    target.faults.add(kind);

    if (kind === "exception_burst") {
      this.push({ kind: "error", source: "checkout-api", text: "PHX-2293 TypeError in apply_tax · 1 event" });
      const fresh: Incident = {
        id: "PHX-2293",
        service: "checkout-api",
        exception: "TypeError",
        message: "unsupported operand type(s) for +: 'NoneType' and 'Decimal'",
        severity: "critical",
        count: 1,
        usersAffected: 1,
        firstSeen: new Date().toISOString(),
        lastSeen: new Date().toISOString(),
        stage: "open",
        request: {
          method: "POST",
          path: "/v2/checkout",
          status: 500,
          userAgent: "storefront-web/3.11.0",
          releaseSha: "9c41ab7",
        },
        frames: [
          {
            file: "app/services/tax.py",
            line: 57,
            fn: "apply_tax",
            code: "return total + region.vat_amount",
            blame: true,
          },
        ],
        fix: {
          summary: "Treat a missing regional VAT as zero",
          reasoning:
            "region.vat_amount is null for the four regions added last week. Every other tax path already defaults to zero; this one does not.",
          branch: "phoenix/fix-missing-vat-amount",
          testsRun: 214,
          testsPassed: 214,
          hunks: [
            {
              file: "app/services/tax.py",
              startLine: 55,
              removed: ["    return total + region.vat_amount"],
              added: ['    return total + (region.vat_amount or Decimal("0"))'],
            },
          ],
        },
      };
      this.incidents = [fresh, ...this.incidents];
    } else {
      const labels: Record<Exclude<FaultKind, "exception_burst">, string> = {
        memory_leak: "resident memory climbing · watching for the limit",
        cpu_spike: "cpu above 90% of one core for 3 samples",
        slow_dependency: "postgres round trip p95 over 500ms",
      };
      this.push({ kind: "warn", source: "checkout-api", text: labels[kind] });
    }
    this.emit();
  }

  clearFaults() {
    for (const sim of this.sims) {
      sim.faults.clear();
      sim.drift = 0;
    }
    this.incidents = this.incidents.filter((i) => i.id !== "PHX-2293");
    this.push({ kind: "info", source: "phoenix-sdk", text: "injected faults cleared · baseline restored" });
    this.emit();
  }

  /** Advance an incident through the repair pipeline. */
  setStage(id: string, stage: Incident["stage"], patch?: Partial<Incident["fix"]>) {
    this.incidents = this.incidents.map((inc) =>
      inc.id === id ? { ...inc, stage, fix: inc.fix ? { ...inc.fix, ...patch } : inc.fix } : inc,
    );
    const notes: Partial<Record<Incident["stage"], string>> = {
      reproducing: "cloned at 9c41ab7 into sandbox · replaying the failing frame",
      patching: "reproduced · drafting a minimal patch",
      testing: "patch written · running the full test suite",
      awaiting_review: "214 of 214 tests pass · waiting on your review",
      pr_open: "pull request opened",
      declined: "patch declined · incident left open",
    };
    const note = notes[stage];
    if (note) this.push({ kind: stage === "pr_open" ? "repair" : "info", source: "code-agent", text: `${id} ${note}` });
    this.emit();
  }
}

export const engine = new TelemetryEngine();
