# Phoenix Frontend Audit

Audit date: 2026-10-03. Read-only: no existing file was modified. `npm install` was run in `frontend/`, which created `frontend/node_modules/` and did not change `package-lock.json`.

**Bottom line:** the frontend is a polished React prototype that runs **entirely on mock data**. It does not start cleanly as it stands: it compiles nothing past the landing page because a whole source folder (`src/lib/`) is missing from the repo. The incident detail UI (traceback, diff, repair steps, PR state) is the most reusable part. Everything that talks to a real backend is dead code from an older "container monitoring" version of the project.

---

## 1. Tech stack

| Item | Value |
|---|---|
| Framework | React 19 (`react`/`react-dom` 19.2.8, installed as peer deps, **not listed in `package.json`**) |
| Language | TypeScript ~6.0 (strict-ish: `noUnusedLocals`, `noUnusedParameters`, `erasableSyntaxOnly`) |
| Routing | `react-router-dom` 7 (`BrowserRouter`) |
| Styling | Tailwind CSS v4 via `@tailwindcss/vite`, custom theme tokens in `src/index.css` (`ash-*`, `bone-*`, `sodium`, `brick`, `jade`, `iris`), Google Fonts (Bricolage Grotesque, Instrument Sans, IBM Plex Mono) |
| Build tool | Vite 8 (`@vitejs/plugin-react`) |
| Package manager | npm (`package-lock.json`, lockfile v3) |
| Other deps | `axios`, `socket.io-client`, `lucide-react` (icons), `recharts`, `framer-motion`, `react-hot-toast`. Of these, only `lucide-react` is used by routed pages; `axios`, `socket.io-client`, `recharts`, `react-hot-toast` are used only by orphaned legacy files; `framer-motion` and `autoprefixer` are unused. |
| Entry | `index.html` → `src/main.tsx` → `src/App.tsx` |

### How to run locally

```bash
cd frontend
npm install
npm run dev          # Vite on http://localhost:3000 (port set in vite.config.ts)
```

- `.claude/launch.json` instead runs `npm run dev -- --port 5183 --strictPort`.
- `npm run build` = `tsc && vite build`.
- Env var: `VITE_BACKEND_URL` (default `http://localhost:5000`), read in `src/api/client.ts` and `src/hooks/useSocket.ts`.
- Docker: `frontend/Dockerfile` runs the dev server on `node:18-alpine` (see issue below).

---

## 2. Does it run?

**Partially. The dev server starts, but every page except the bare HTML shell fails.**

Tested on Node 22.16.0 / npm 10.9.2:

| Step | Result |
|---|---|
| `npm install` | ✅ 142 packages, exit 0. 1 high-severity advisory (axios ≤ 1.19.0, several prototype-pollution/ReDoS CVEs). |
| `npx vite --port 3000` | ✅ "ready in ~13s" |
| `GET /`, `/src/main.tsx`, `/src/App.tsx` | ✅ 200 |
| `GET /src/pages/Dashboard.tsx`, `/src/components/chrome/Site.tsx`, … | ❌ **500** |
| `npx tsc --noEmit` | ❌ 17 errors, all `TS2307: Cannot find module '…/lib/cn'` or `'…/lib/format'` |

### Error

```
[vite] Pre-transform error: Failed to resolve import "../lib/cn" from "src/pages/Dashboard.tsx". Does the file exist?
[vite] Pre-transform error: Failed to resolve import "../../lib/format" from "src/components/dashboard/IncidentPanel.tsx". Does the file exist?
… (14 files total)
```

Because `App.tsx` imports `Site.tsx`, which imports `lib/cn`, the app renders a blank page / Vite error overlay on **every** route.

### Root cause

The repo-root `.gitignore` (line 17) contains the Python template rule `lib/`. It matches `frontend/src/lib/` too, so that folder was never committed. The code was written against it, it just never made it into the repo.

### Likely fix (not applied)

1. Change the root `.gitignore` rule from `lib/` to `/lib/` (root only), or add `!frontend/src/lib/`.
2. Recover `frontend/src/lib/` from whoever wrote it, or recreate it. The call sites need exactly:
   - `lib/cn.ts`: `cn(...classes: Array<string | false | null | undefined>): string` (join truthy class names; used by 14 files).
   - `lib/format.ts`:
     - `since(iso: string): string`: relative time ("3h ago"); used by `Connect.tsx`, `IncidentPanel.tsx`.
     - `clock(epochMs: number): string`: wall-clock time ("16:19:05"); used by `Panels.tsx` (event feed).
     - `duration(seconds: number): string`: uptime ("4d 18h"); used by `ProcessTable.tsx`.

TypeScript reports no other errors, so with these two files restored the app should compile and run.

### Other run issues

| Issue | Where | Impact |
|---|---|---|
| Docker image uses `node:18-alpine` | `frontend/Dockerfile` | Vite 8 requires Node 20.19+ / 22.12+. The container will very likely fail to start. Use `node:22-alpine`. |
| `react` / `react-dom` not declared | `package.json` | Works only because npm auto-installs peer deps of `react-router-dom`. Should be explicit dependencies. |
| `@types/react-router-dom@5` | `package.json` | Types for router v5; v7 ships its own types. Harmless but stale. |
| axios high-severity advisory | `package.json` | `npm audit fix` would bump it. |
| Vite proxy is bypassed | `vite.config.ts` vs `src/api/client.ts` | Proxy forwards `/api` and `/socket.io` to `:5000`, but the client uses an absolute `http://localhost:5000` base URL, so the proxy is never used and the backend must allow CORS. |

---

## 3. Pages, routes and components

### Routed (live) pages, from `src/App.tsx`

| Route | Page | Layout | What it shows | Data source |
|---|---|---|---|---|
| `/` | `pages/Home.tsx` | Site header/footer (`components/chrome/Site.tsx`) | Marketing landing page: hero, animated "traceback → patch → PR" demo (`signature/HealingTraceback.tsx`), "how it works", install snippet (`pip install phoenix-sdk` / `phoenix.init(...)`), limits section, CTA. | `mock/incidents.ts` (`HERO_INCIDENT`) |
| `/connect` | `pages/Connect.tsx` | Site layout | Two-step GitHub flow. **Step 1 `SignIn`:** lists requested GitHub scopes, "Continue with GitHub" button (fake, 850 ms timeout, then signs in a hardcoded user). **Step 2 `Picker`:** repo list with filter, animated "scanning manifests for phoenix-sdk" per repo, install snippet + "scan again" for repos missing the SDK, "Open the dashboard" button. | `mock/repos.ts`, `state/SessionContext.tsx` (sessionStorage) |
| `/app` and `/app/:owner/:repo` | `pages/Dashboard.tsx` | Own header (`chrome/AppHeader.tsx`) | Demo banner, one-sentence process status, metric strip (CPU/memory/p95/error rate), trend chart, process table, live event feed, **incident list with expandable repair detail**, and "walkthrough controls" to inject faults. | `mock/engine.ts` via `hooks/useEngine.ts` |
| `*` | `pages/NotFound.tsx` | Site layout | 404 with link home. | none |

### Main components used by live pages

| Component | What it does |
|---|---|
| `chrome/Site.tsx` | Marketing header (anchor links to `/#how`, `/#install`, `/#limits`, plus Dashboard/Connect) and footer. |
| `chrome/AppHeader.tsx` | Dashboard top bar: `owner/repo`, branch, "Switch" (→ `/connect`), release chip (hardcoded `9c41ab7`), "Live · 1.5s" dot, user initials. |
| `dashboard/IncidentPanel.tsx` → `IncidentList` + `Detail` | **The core Phoenix UI.** Collapsible incident rows (exception, message, ID, service, event count, stage chip). Expanded: traceback, request context (method/path/status/release/client/first seen), then by stage: "Fix this" button, 4-step progress (Reproduce → Patch → Test → Review), patch summary + reasoning + diff + `testsPassed/testsRun` chip + branch, "Open pull request" / "Decline" buttons, PR-open banner, or "unfixable" note. |
| `code/Traceback.tsx` → `TracebackView`, `DiffView` | Python traceback renderer (blame-frame highlight) and unified-diff renderer with line numbers and syntax highlighting (`code/py.tsx`). |
| `dashboard/MetricStrip.tsx` | CPU / memory / p95 / error-rate tiles with sparklines; memory footnote. |
| `dashboard/ProcessTable.tsx` | Table of reporting processes (name, role, runtime, PID, uptime, status, sparkline). |
| `dashboard/Panels.tsx` → `EventFeed`, `FailurePanel` | Scrolling log-style feed; buttons to inject memory leak / CPU spike / slow dependency / exception. |
| `charts/Chart.tsx` → `Trend`, `Sparkline` | Hand-rolled SVG charts (not Recharts). |
| `signature/HealingTraceback.tsx` | Animated landing-page demo. |
| `code/CodeSurface.tsx` | Tabbed code pane + copyable command line. |
| `ui/Button.tsx`, `ui/Primitives.tsx` (`Chip`, `Dot`, `Label`, `SectionRule`), `ui/Reveal.tsx`, `brand/Wordmark.tsx` | Design-system primitives. |

### Orphaned files (not reachable from any route)

These compile but nothing imports them. They are from the older Flask/MongoDB "container monitoring" version (old dark slate/violet Tailwind look):

| File | What it showed |
|---|---|
| `pages/Overview.tsx` | Stat cards (active / resolved / "auto recoveries" / monitored containers), container grid, escalation alert, recent incidents. |
| `pages/Containers.tsx` | Grid of `ContainerCard`s (status, CPU, memory, restarts). |
| `pages/Metrics.tsx` | Recharts CPU/memory history per service. |
| `pages/Logs.tsx` | Log lines derived from incidents per container. |
| `pages/Incidents.tsx` | Searchable/filterable incident table. |
| `pages/IncidentDetail.tsx` | Incident header, root cause, confidence bar, timeline, Grok summary/recommendations, metric snapshot. |
| `pages/AIAdvisor.tsx` | Aggregated "Grok-3 Powered" recommendations. |
| `pages/Settings.tsx` | Static settings page ("Grok-3 (Active)"). |
| `components/Sidebar.tsx`, `ContainerCard.tsx`, `MetricCard.tsx`, `EscalationAlert.tsx`, `StatusBadge.tsx`, `IncidentTimeline.tsx`, `ConfidenceBar.tsx`, `AISummaryPanel.tsx` | Supporting components for the above. |
| `hooks/useIncidents.ts`, `useMetrics.ts`, `useSocket.ts`, `api/*.ts`, `types/index.ts` | The only code that calls a real backend (see §4). |
| `main.ts`, `counter.ts`, `style.css`, `assets/hero.png`, `assets/typescript.svg`, `assets/vite.svg`, `public/icons.svg` | Untouched Vite "vanilla-ts" starter template. `main.ts` targets `#app`, which doesn't exist. |

---

## 4. Backend calls

### Live pages: **zero real API calls**

Every live page reads from in-browser mocks:

| Mock | Pretends to be | Used by |
|---|---|---|
| `mock/engine.ts` (`TelemetryEngine`) | "socket.io feed of `sample` and `incident` events" | `Dashboard.tsx`, `IncidentPanel.tsx`, `Panels.tsx` via `useEngine()` |
| `mock/incidents.ts` | `GET /api/incidents` | `engine.ts`, `Home.tsx` |
| `mock/repos.ts` | `GET /api/github/user`, `GET /api/github/repos` | `Connect.tsx`, `Dashboard.tsx`, `SessionContext.tsx` |

Hardcoded values on live pages (beyond the mocks):

- `MOCK_USER` login `"Rudranshhhhh"` (`mock/repos.ts`); sign-in sets it with no network call. The page itself says "This build signs you in locally."
- Default repo `phoenix-labs/orbital-checkout` when none is selected (`Dashboard.tsx:89`).
- Release `"9c41ab7"` in `AppHeader` (`Dashboard.tsx:106`).
- Footer text "Phoenix has opened 3 pull requests … You merged 2." (`Dashboard.tsx:222`).
- PR number invented client-side: `1200 + count % 90` (`IncidentPanel.tsx:751`).
- Repair progress is `setTimeout` beats (0 / 1.6 / 3.4 / 5.7 s) calling `engine.setStage` (`IncidentPanel.tsx:737-748`).
- SDK "rescan" always succeeds with `phoenix-sdk 0.4.2` after 1.1 s (`Connect.tsx:425-433`).

### Real API client (orphaned code only)

Base URL: `src/api/client.ts`: `import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000'`, axios with JSON content type, no auth headers. `docker-compose.yml` sets `VITE_BACKEND_URL=http://localhost:5000`.

| Function | Method + URL | Request | Expected response | Exists in current backend? |
|---|---|---|---|---|
| `getIncidents` | `GET /api/incidents` | query: `service, status, severity, resolved, page, page_size` | `{ items: Incident[], total, page, page_size, pages }` | Yes (Flask, as `/api/incidents/`, so a trailing-slash redirect) |
| `getIncidentById` | `GET /api/incidents/{id}` | – | `Incident` | Yes |
| `getDashboardSummary` | `GET /api/incidents/summary` | – | `{ total_incidents, active_incidents, resolved_incidents, escalated_incidents }` | Yes |
| `getLatestMetrics` | `GET /api/metrics` | – | `MetricSnapshot[]` | Yes |
| `getMetricsForService` | `GET /api/metrics/{service}` | query: `hours` | `MetricSnapshot[]` | Yes |
| `getContainers` | `GET /api/containers` | – | `ContainerState[]` (`service, container_status, cpu_percent, memory_percent, memory_mb, restart_count, health_status, last_seen`) | Yes |
| `getAISummary` | `GET /api/ai/summary/{id}` | – | `{ summary: string }` | **No** (never implemented; also never called) |
| `getAIRecommendations` | `GET /api/ai/recommendations` | – | `{ recommendations: string[] }` | **No** |

Old `Incident` shape (`types/index.ts`): `incident_id, service, container_name, failure_type (CONTAINER_DOWN|HIGH_CPU|…), severity (LOW…CRITICAL), confidence_score, status (DETECTED|DIAGNOSING|RECOVERING|VERIFYING|ESCALATED|RESOLVED), root_cause, grok_summary, grok_recommendations, metrics_snapshot, recovery_strategy, retry_count, resolved, *_at timestamps, timeline[]`.

> Note: the current `backend/` is **Flask + Flask-SocketIO + MongoDB**, not FastAPI. Its API is the container-monitoring API above. Nothing in it serves the new Phoenix flow.

### Two incompatible type systems

| | `types/index.ts` (old, orphaned) | `types/phoenix.ts` (new, live) |
|---|---|---|
| ID field | `incident_id` | `id` (e.g. `PHX-2291`) |
| Status | `status`: `DETECTED…RESOLVED` | `stage`: `open, reproducing, patching, testing, awaiting_review, pr_open, declined, unfixable` |
| Error | `failure_type`, `root_cause` | `exception`, `message`, `frames[]` |
| Fix | `grok_summary`, `grok_recommendations` | `fix: { summary, reasoning, hunks[], testsRun, testsPassed, branch, prNumber }` |
| Casing | snake_case | camelCase |

Neither matches the Phoenix status model (`detected → diagnosing → fix_proposed → validating → validated/rejected → pr_opened`).

---

## 5. Live updates (WebSockets / polling)

| Mechanism | Where | Status |
|---|---|---|
| **Simulated stream**: `setInterval` every 1500 ms, pub/sub to React | `mock/engine.ts` → `useEngine()` | **Live** (powers the dashboard). Comment says: "Replace the engine subscription with the socket feed later." |
| `setTimeout` chains to fake progress | `IncidentPanel.tsx` (repair stages), `Connect.tsx` (manifest scan, sign-in) | Live, but fake |
| **Socket.IO client** (`socket.io-client`, `transports: ['websocket']`) | `hooks/useSocket.ts` | Orphaned |
| Namespace `/incidents`, event `incident_update` (upserts list, refetches summary, shows toasts) | `hooks/useIncidents.ts` | Orphaned |
| Namespace `/metrics`, event `metric_update` | `hooks/useMetrics.ts` | Orphaned |
| Backend also emits `escalation_alert` on `/incidents` | `backend/websocket/events.py` | No frontend listener anywhere |
| HTTP polling against a real API | – | **None** |

Implication for FastAPI: Socket.IO is not native to FastAPI (needs `python-socketio` ASGI mounting). Since the dashboard only needs server→client pushes, **Server-Sent Events** (or a plain FastAPI `WebSocket`) is simpler, and `useEngine()`'s subscribe shape is easy to back with either. Polling `GET /api/incidents/{id}` every 2–3 s while an incident is in a non-terminal state would also work and is the least effort.

---

## 6. Coverage against Phoenix needs

### ✅ Already covered (UI exists, only needs real data)

| Need | Where |
|---|---|
| Error + stack trace display | `TracebackView` (`code/Traceback.tsx`): frames with file/line/function/code, blame-frame highlight, exception + message. Good Python syntax highlighting. |
| Proposed patch (diff) | `DiffView`: per-file hunks with line numbers, add/remove colouring, highlighting. |
| Incident list with per-incident expand | `IncidentList` in `dashboard/IncidentPanel.tsx` |
| Visual pipeline progress | `Steps` component (4-step tracker with done/current/pending states) |
| Branch name display | `incident.fix.branch` shown in detail |
| Empty state | "Nothing has thrown since the reporter attached." |
| Repo context in the app header + "Switch" repo | `AppHeader` |

### 🟡 Partly covered (exists, needs changes)

| Need | What exists | What to change |
|---|---|---|
| **Incident statuses** | `RepairStage`: `open, reproducing, patching, testing, awaiting_review, pr_open, declined, unfixable` | Replace with `detected, diagnosing, fix_proposed, validating, validated, rejected, pr_opened`. Update `stageChip()`, `STEPS`/`ORDER` (e.g. Detect → Diagnose → Propose fix → Validate → PR) and the `Detail` branching. |
| **LLM root cause + explanation** | `fix.summary` + `fix.reasoning` render as the patch headline and paragraph | Root cause is a diagnosis, not part of the fix. Add a separate "Root cause" block (cause, explanation, optionally blamed file/line and confidence) that shows from `diagnosing`/`fix_proposed` onward, even when no patch exists. |
| **Sandbox validation result** | One chip: `testsPassed/testsRun tests pass` | Add explicit PASS/FAIL badge, collapsible **test output** (stdout/stderr), **"original bug still reproduces?"** yes/no, duration, and a `rejected` view with the failure reason. |
| **PR link** | `#prNumber on branch` banner, with no link | Use a real `pr_url` and render an anchor to GitHub. PR number must come from the backend, not `1200 + count % 90`. |
| **Connect a GitHub repo** | Full two-step UI (scopes, repo picker, filter) | Sign-in is fake; the picker scans for `phoenix-sdk` in manifests, which does not match Phoenix's flow (Docker logs + GitHub Actions). Replace with real GitHub OAuth/App install, list repos from the API, and "connect" = register repo (+ optionally Docker container name / Actions workflow). Drop the SDK scan or turn it into "checks: Actions enabled, Dockerfile found". |
| **Request context sidebar** | Method/path/status/release/client/users affected | Phoenix's sources are runtime logs and failed Actions runs. Replace with: source (`docker_logs`/`github_actions`), container or workflow run link, commit SHA, detected-at. |
| **Human action buttons** | "Fix this", "Open pull request", "Decline", "Try a different patch" | Spec says PR opens automatically on PASS. Decide whether a human gate exists. If not, remove these; if so, wire them to endpoints (`/retry`, `/open-pr`, `/reject`). |
| **Event feed** | Fake log feed of SDK/agent lines | Could become a real per-incident timeline/activity log (status transitions with timestamps), backed by the API. |
| **Live updates** | Mock 1.5 s ticker | Replace `useEngine` with SSE/WebSocket/polling against the FastAPI server (see §5). |
| **Incident ID format** | `PHX-2291` | Phoenix uses `INC-001` (branch `phoenix/fix/INC-001`). Cosmetic, but mocks/copy should match. |
| **Landing page copy** | Sells "install one Python package / phoenix.init()" | Rewrite install section to the real onboarding (connect repo, Docker/Actions). Keep the visual design. |

### ❌ Missing entirely

| Need | Notes |
|---|---|
| Any real API integration on live pages | No `fetch`/axios call on a reachable route. |
| Single-incident page / deep link (`/app/:owner/:repo/incidents/:id`) | Only the expand-in-list view; can't share a link to one incident. |
| Test output viewer | No component for raw sandbox logs. |
| "Original bug still reproduces" indicator | Not modelled anywhere. |
| Detection source (runtime log vs failed GitHub Actions run) + link to the Actions run | Not modelled. |
| Collected source-code context shown to the user (files sent to the LLM) | Not modelled. Optional, but useful for trust. |
| Real authentication / session | `SessionContext` stores a mock user in `sessionStorage`. |
| Loading and error states for network calls | Live pages never wait on the network, so there are none. |
| Filtering/searching incidents by status | Only existed in the orphaned `Incidents.tsx`. |
| Multiple-hunk / multi-file patch from a raw unified diff | `DiffView` takes pre-split `{removed[], added[]}` per hunk and treats each hunk as "all removals then all additions". A real LLM diff (interleaved context/+/- lines) needs a parser and per-line types. |

---

## 7. Leftovers from older project directions

### In live (routed) code: visible to users today

| Leftover | Location |
|---|---|
| CPU / memory / p95 / error-rate metric strip | `dashboard/MetricStrip.tsx`, used at top of `Dashboard.tsx` |
| CPU/memory trend chart with series tabs | `Dashboard.tsx` (`SERIES`, `Trend`) |
| Process table (PID, uptime, runtime, role, status sparkline) | `dashboard/ProcessTable.tsx` |
| Process "health" verdict sentence (memory climbing, CPU pinned, …) | `verdict()` in `Dashboard.tsx` |
| Fault injection: memory leak, CPU saturation, slow dependency | `FailurePanel` in `dashboard/Panels.tsx`, `FAULTS` in `mock/engine.ts` |
| "Live · 1.5s" telemetry indicator | `AppHeader.tsx` |
| SDK-based model (`phoenix-sdk`, `phoenix.init`, "reporter attached", manifest scanning) | `Home.tsx`, `Connect.tsx`, `mock/repos.ts`, `mock/engine.ts` |

### In orphaned code: safe to delete once confirmed

| Leftover | Location |
|---|---|
| **"Grok" labels** | `AISummaryPanel.tsx:43` ("Grok-3 Powered"), `AIAdvisor.tsx:10-38`, `Settings.tsx:89` ("Grok-3 (Active)"), `IncidentDetail.tsx:118-119`, `types/index.ts:69-70` (`grok_summary`, `grok_recommendations`) |
| Container CPU/memory cards, restart counts | `ContainerCard.tsx`, `pages/Containers.tsx`, `pages/Overview.tsx` |
| Health/container grid, "Monitored Containers", "Auto Recoveries" stats | `pages/Overview.tsx`, `MetricCard.tsx` |
| CPU/memory history charts | `pages/Metrics.tsx` (Recharts) |
| Escalation alerts (`ESCALATED` status, restart-based recovery) | `EscalationAlert.tsx`, `useIncidents.ts` toasts ("Phoenix is recovering … using {recovery_strategy}") |
| Failure types `CONTAINER_DOWN, HIGH_CPU, HIGH_MEMORY, DATABASE_UNREACHABLE, REDIS_DOWN, …` | `types/index.ts` |
| `/api/containers`, `/api/metrics`, `/socket.io` `/metrics` namespace | `api/metrics.ts`, `hooks/useMetrics.ts`, `vite.config.ts` proxy |
| Vite starter template | `main.ts`, `counter.ts`, `style.css`, `assets/*`, `public/icons.svg` |

No restart/scale **buttons** exist in the frontend (only restart *counts* in `ContainerCard`). Restart logic lives in the old `agent/recovery/strategies/restart_*.py`.

### Elsewhere in the repo (outside the frontend, for awareness)

- `backend/` is Flask + MongoDB for container metrics; `backend/package-lock.json` is an empty stray file.
- `agent/ai/grok_client.py`, `.env.example` (`GROK_API_KEY`, `GROK_MODEL`, `FLASK_ENV`, `POLL_DOCKER_SECONDS`, …).
- `Makefile` demo targets (`demo-leak`, `demo-cpu`, `demo-db`, `demo-redis`) and `docker-compose.yml` with Postgres/Redis sample stack.
- Root `.gitignore` `lib/` rule (the cause of the build failure).

---

## 8. FastAPI endpoints this frontend will need

Conventions suggested: JSON, snake_case on the wire (map to camelCase in a single adapter module that replaces `src/mock/`), ISO-8601 UTC timestamps, IDs like `INC-001`. Prefix everything with `/api`. Enable CORS for the dev origin (`http://localhost:3000`) or switch `client.ts` to relative URLs and use the existing Vite proxy.

### 8.1 Shared incident model

```json
{
  "id": "INC-001",
  "repo": "acme/orders-api",
  "status": "validated",
  "source": {
    "type": "github_actions",
    "workflow_run_url": "https://github.com/acme/orders-api/actions/runs/123456",
    "container": null,
    "commit_sha": "9c41ab7"
  },
  "error": {
    "exception_type": "TypeError",
    "message": "unsupported operand type(s) for *: 'Decimal' and 'NoneType'",
    "stack_trace": "Traceback (most recent call last):\n  File \"app/pricing.py\", line 84, in price_after_discount\n ...",
    "frames": [
      { "file": "app/api/checkout.py", "line": 61, "function": "post_checkout", "code": "total = price_after_discount(cart, promo)", "blame": false },
      { "file": "app/pricing.py", "line": 84, "function": "price_after_discount", "code": "return subtotal - (subtotal * promo.percent / 100)", "blame": true }
    ]
  },
  "diagnosis": {
    "root_cause": "promo.percent is None for flat-amount promos",
    "explanation": "Flat-discount promos store the amount in promo.amount and leave percent null; the pricing path assumes a percentage.",
    "suspect_file": "app/pricing.py",
    "suspect_line": 84,
    "confidence": 0.86,
    "model": "claude-sonnet-5-5",
    "context_files": ["app/pricing.py", "app/models/promo.py"]
  },
  "patch": {
    "summary": "Handle flat-amount promos in price_after_discount",
    "diff": "--- a/app/pricing.py\n+++ b/app/pricing.py\n@@ -82,3 +82,6 @@\n ...",
    "files_changed": ["app/pricing.py"]
  },
  "validation": {
    "result": "PASS",
    "tests_run": 42,
    "tests_passed": 42,
    "bug_reproduces_after_patch": false,
    "bug_reproduced_before_patch": true,
    "duration_seconds": 38.2,
    "output": "============ 42 passed in 37.91s ============",
    "finished_at": "2026-10-03T10:14:22Z"
  },
  "pull_request": {
    "number": 17,
    "url": "https://github.com/acme/orders-api/pull/17",
    "branch": "phoenix/fix/INC-001",
    "state": "open"
  },
  "timeline": [
    { "status": "detected",     "at": "2026-10-03T10:12:01Z", "message": "Failed run #123456 on main" },
    { "status": "diagnosing",   "at": "2026-10-03T10:12:03Z", "message": null },
    { "status": "fix_proposed", "at": "2026-10-03T10:13:10Z", "message": null },
    { "status": "validating",   "at": "2026-10-03T10:13:12Z", "message": null },
    { "status": "validated",    "at": "2026-10-03T10:14:22Z", "message": "42/42 tests pass" },
    { "status": "pr_opened",    "at": "2026-10-03T10:14:30Z", "message": "PR #17" }
  ],
  "created_at": "2026-10-03T10:12:01Z",
  "updated_at": "2026-10-03T10:14:30Z"
}
```

`diagnosis`, `patch`, `validation`, `pull_request` are `null` until that stage is reached. On `rejected`, `validation.result = "FAIL"` and an optional `"rejection_reason"` string. Sending the patch as a raw unified `diff` (rather than pre-split hunks) is recommended; the frontend should parse it.

### 8.2 Incidents

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `GET /api/incidents` | List for the dashboard | query: `repo`, `status` (comma list), `page` (1), `page_size` (20) | `{"items": [IncidentSummary], "total": 12, "page": 1, "page_size": 20}` |
| `GET /api/incidents/{id}` | Full detail | – | full Incident (§8.1) |
| `GET /api/incidents/stats` | Header counts | query: `repo` | `{"total": 12, "by_status": {"detected": 1, "diagnosing": 0, "fix_proposed": 1, "validating": 1, "validated": 0, "rejected": 2, "pr_opened": 7}}` |
| `GET /api/incidents/{id}/validation/log` *(optional)* | Large raw test output, if kept out of the detail payload | – | `text/plain` |

`IncidentSummary` (list row):

```json
{
  "id": "INC-001",
  "repo": "acme/orders-api",
  "status": "pr_opened",
  "exception_type": "TypeError",
  "message": "unsupported operand type(s) for *: 'Decimal' and 'NoneType'",
  "source_type": "github_actions",
  "validation_result": "PASS",
  "pr_url": "https://github.com/acme/orders-api/pull/17",
  "created_at": "2026-10-03T10:12:01Z",
  "updated_at": "2026-10-03T10:14:30Z"
}
```

### 8.3 Incident actions (only if a human-in-the-loop is kept)

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /api/incidents/{id}/retry` | Re-run diagnosis + patch (replaces "Try a different patch" / "Fix this") | `{"hint": "optional extra context"}` | `202 {"id": "INC-001", "status": "diagnosing"}` |
| `POST /api/incidents/{id}/pull-request` | Open PR manually for a `validated` incident | `{}` | `201 {"number": 17, "url": "…", "branch": "phoenix/fix/INC-001"}` |
| `POST /api/incidents/{id}/dismiss` | Close without a PR (replaces "Decline") | `{"reason": "not a real bug"}` | `200 {"id": "INC-001", "status": "rejected"}` |

### 8.4 Live updates

| Method + path | Purpose | Response |
|---|---|---|
| `GET /api/events?repo=acme/orders-api` (SSE, `text/event-stream`) | Push status changes so the list/detail update without refresh | `event: incident.updated`<br>`data: {"id": "INC-001", "status": "validating", "updated_at": "…"}`<br><br>`event: incident.created`<br>`data: IncidentSummary` |

The client refetches `GET /api/incidents/{id}` on `incident.updated` for the open incident. Alternative: `WS /api/ws` with the same message shapes, or polling.

### 8.5 GitHub connection and repos

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `GET /api/auth/github/login` | Start OAuth / GitHub App install | – | `302` to GitHub |
| `GET /api/auth/github/callback` | OAuth callback; sets session cookie | query: `code`, `state` | `302` to `/connect` |
| `GET /api/auth/me` | Current user (replaces `MOCK_USER`) | – | `{"login": "octocat", "name": "…", "avatar_url": "…"}` or `401` |
| `POST /api/auth/logout` | Sign out | – | `204` |
| `GET /api/github/repos` | Repos the user can connect (replaces `mock/repos.ts`) | query: `q` | `[{"id": 123, "full_name": "acme/orders-api", "private": true, "language": "Python", "default_branch": "main", "pushed_at": "…", "description": "…", "connected": false}]` |
| `GET /api/repos` | Repos Phoenix is watching | – | `[{"id": "acme/orders-api", "default_branch": "main", "sources": {"github_actions": true, "docker_container": "orders-api"}, "connected_at": "…", "open_incidents": 2}]` |
| `POST /api/repos` | Connect a repo | `{"full_name": "acme/orders-api", "watch_actions": true, "docker_container": "orders-api", "test_command": "pytest -q"}` | `201` repo object |
| `GET /api/repos/{owner}/{repo}` | Repo detail for the dashboard header | – | repo object + `{"last_commit_sha": "9c41ab7"}` |
| `DELETE /api/repos/{owner}/{repo}` | Disconnect | – | `204` |
| `GET /api/repos/{owner}/{repo}/checks` *(optional)* | Replaces SDK scan: readiness checks | – | `{"python": true, "dockerfile": "Dockerfile", "workflows": [".github/workflows/ci.yml"], "tests_found": true}` |

### 8.6 Ops

| Method + path | Response |
|---|---|
| `GET /api/health` | `{"status": "ok", "version": "0.1.0", "components": {"db": "ok", "github": "ok", "sandbox": "ok", "llm": "ok"}}` |

(Ingest endpoints from detectors, e.g. `POST /api/incidents` or a GitHub `workflow_run` webhook at `POST /api/webhooks/github`, are backend-to-backend and not needed by the UI.)

---

## 9. Suggested order of work

1. **Make it build:** fix `.gitignore` `lib/` rule; restore/recreate `src/lib/cn.ts` and `src/lib/format.ts`; bump Dockerfile to `node:22-alpine`; declare `react`/`react-dom`.
2. **Replace the data model:** one `types/phoenix.ts` matching §8.1 with the real statuses; delete `types/index.ts`.
3. **Swap mocks for an API layer:** replace `mock/*` and `useEngine` with `api/` functions + a hook using SSE/polling; add loading/error states.
4. **Rework the incident detail:** split Root cause from Patch, add Validation panel (PASS/FAIL, test output, reproduces?), real PR link, unified-diff parser for `DiffView`, optional `/incidents/:id` route.
5. **Strip leftovers from the dashboard:** metric strip, trend chart, process table, fault-injection panel, "Live · 1.5s"; then delete orphaned legacy pages/components/hooks and the Vite starter files.
6. **Real GitHub connect:** OAuth + repo list + connect form; drop the SDK manifest scan; update landing-page install copy.
