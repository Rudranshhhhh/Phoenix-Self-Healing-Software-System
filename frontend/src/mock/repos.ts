// ---------------------------------------------------------------------------
// Stand-in for GET /api/github/user and /api/github/repos.
// The scan field is what the Phoenix service reports after reading each repo's
// requirements.txt / pyproject.toml / Pipfile looking for phoenix-sdk.
// ---------------------------------------------------------------------------

import type { GithubUser, Repository, SdkScan } from "../types/phoenix";

export const MOCK_USER: GithubUser = {
  login: "Rudranshhhhh",
  name: "Rudransh",
  avatarUrl: "",
  company: "Phoenix Labs",
};

/** Manifests Phoenix looks in, in order. Shown verbatim in the UI. */
export const MANIFESTS = ["requirements.txt", "pyproject.toml", "Pipfile", "setup.cfg"];

interface RepoSeed extends Omit<Repository, "scan"> {
  result: SdkScan;
}

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

const SEEDS: RepoSeed[] = [
  {
    id: 1,
    owner: "Rudranshhhhh",
    name: "orbital-checkout",
    private: true,
    language: "Python",
    pushedAt: hoursAgo(3),
    defaultBranch: "main",
    description: "Payments and checkout for the storefront. FastAPI + Postgres.",
    result: { state: "installed", version: "0.4.2", foundIn: ".github/workflows/tests.yml", line: 14 },
  },
  {
    id: 2,
    owner: "Rudranshhhhh",
    name: "atlas-inventory",
    private: true,
    language: "Python",
    pushedAt: hoursAgo(19),
    defaultBranch: "main",
    description: "Stock levels, reservations, and warehouse sync.",
    result: { state: "outdated", version: "0.2.9", latest: "0.4.2", foundIn: ".github/workflows/ci.yml", line: 31 },
  },
  {
    id: 3,
    owner: "Rudranshhhhh",
    name: "ledger-api",
    private: false,
    language: "Python",
    pushedAt: hoursAgo(52),
    defaultBranch: "main",
    description: "Double-entry ledger service. Flask, heavy Celery use.",
    result: { state: "missing", checked: MANIFESTS },
  },
  {
    id: 4,
    owner: "phoenix-labs",
    name: "sentinel-worker",
    private: true,
    language: "Python",
    pushedAt: hoursAgo(6),
    defaultBranch: "develop",
    description: "Background jobs: invoicing, exports, nightly reconciliation.",
    result: { state: "installed", version: "0.4.2", foundIn: ".github/workflows/test.yml", line: 22 },
  },
  {
    id: 5,
    owner: "phoenix-labs",
    name: "storefront-web",
    private: false,
    language: "TypeScript",
    pushedAt: hoursAgo(11),
    defaultBranch: "main",
    description: "Next.js storefront. No Python entrypoint for the SDK to wrap.",
    result: { state: "missing", checked: ["package.json"] },
  },
  {
    id: 6,
    owner: "Rudranshhhhh",
    name: "notify-relay",
    private: true,
    language: "Python",
    pushedAt: hoursAgo(96),
    defaultBranch: "main",
    description: "Email, SMS and webhook fan-out.",
    result: { state: "missing", checked: MANIFESTS },
  },
];

/** Repos as they arrive from GitHub, before Phoenix has scanned them. */
export function repositoriesPending(): Repository[] {
  return SEEDS.map(({ result: _result, ...repo }) => ({ ...repo, scan: { state: "pending" } }));
}

/** What the scan finds for a given repo id. */
export function scanResult(id: number): SdkScan {
  return SEEDS.find((s) => s.id === id)?.result ?? { state: "missing", checked: MANIFESTS };
}

export function findRepository(owner: string, name: string): Repository | undefined {
  const seed = SEEDS.find((s) => s.owner === owner && s.name === name);
  if (!seed) return undefined;
  const { result, ...repo } = seed;
  return { ...repo, scan: result };
}
