# phoenix-api

Phoenix API — serves incidents to the dashboard. Real incidents arrive from the pipeline through
`POST /api/ingest/events` and are stored in a JSON file; demo fixtures (`INC-001`…`INC-008`) are
shown alongside them while `DEMO_FIXTURES=1`.

Models in `app/models.py` mirror `frontend/src/types/incident.ts` field for field.

```bash
cd phoenix-api
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Endpoints (CORS allows `http://localhost:3000`; interactive docs at http://localhost:8000/docs):

- `GET /api/health`
- `GET /api/incidents?status=validated,pr_opened&repo=phoenix-demo/orders-api&page=1&page_size=20`
- `GET /api/incidents/{id}` (404 `{"detail": "Incident not found"}` if unknown)
- `POST /api/ingest/events` (see below)

Demo fixtures: `INC-001`…`INC-007` are one incident per status. `INC-008` is live: it advances one
status every 5 seconds (detected → diagnosing → fix_proposed → validating → validated → pr_opened)
and then starts over. Its clock restarts whenever the server (or `--reload`) restarts.

## Ingest (real pipeline events)

`POST /api/ingest/events` takes one event per pipeline stage from the agent and turns it into a
dashboard incident (the same `Incident` shape the GET routes return). Ingested incidents are kept
in a JSON file and survive restarts. When `PHOENIX_INGEST_TOKEN` is set, send it in the
`X-Phoenix-Token` header; a missing or wrong token gets `401`.

Events (`event` field): `detected`, `diagnosing`, `fix_proposed`, `validating`, `validated`,
`rejected`, `failed` (shown as `rejected`), `pr_opened`. Each event sets the incident's status and
adds a timeline entry. Sections you leave out stay as they were, so later events only need their
own data. Payload field names follow the agent's models (`DiagnosisResult`, `PatchResult`,
`ValidationResult`, `PRResult`); the API builds the stack frames from the traceback, a unified diff
from `old_code`/`new_code`, and test counts from pytest's summary line.

Agent ids (uuids) get dashboard ids `INC-101`, `INC-102`, … in the order they first arrive. Ids
already in `INC-NNN` form are kept as they are.

`detected`, with the error and where it came from:

```json
{
  "incident_id": "3f2a9c1e-7b4d-4e8a-9f10-2c6d5e8b1a47",
  "event": "detected",
  "repo": "phoenix-demo/orders-api",
  "source": {"type": "docker_runtime", "container": "orders-api"},
  "error": {
    "exception_type": "KeyError",
    "message": "'price'",
    "stack_trace": "Traceback (most recent call last):\n  File \"/app/app/main.py\", line 42, in checkout\n    total = cart_total(cart)\n  File \"/app/app/pricing.py\", line 17, in cart_total\n    return sum(item[\"price\"] * item[\"qty\"] for item in cart)\nKeyError: 'price'"
  }
}
```

`fix_proposed`, with the diagnosis and the patch:

```json
{
  "incident_id": "3f2a9c1e-7b4d-4e8a-9f10-2c6d5e8b1a47",
  "event": "fix_proposed",
  "diagnosis": {
    "root_cause": "cart_total reads item[\"price\"], but items from the legacy cart only have unit_price.",
    "explanation": "Legacy cart items store the price under unit_price, so the lookup raises KeyError.",
    "affected_file": "app/pricing.py",
    "affected_line": 17,
    "confidence": 0.8
  },
  "patch": {
    "explanation": "Fall back to unit_price when price is missing.",
    "patches": [
      {
        "file": "app/pricing.py",
        "old_code": "def cart_total(cart):\n    return sum(item[\"price\"] * item[\"qty\"] for item in cart)",
        "new_code": "def cart_total(cart):\n    return sum(item.get(\"price\", item.get(\"unit_price\", 0)) * item[\"qty\"] for item in cart)"
      }
    ]
  }
}
```

`validated` (use `rejected` with `"validated": false` and a `reason` when the patch fails):

```json
{
  "incident_id": "3f2a9c1e-7b4d-4e8a-9f10-2c6d5e8b1a47",
  "event": "validated",
  "validation": {
    "validated": true,
    "reason": "All validation checks passed.",
    "test_stdout": "........\n=== 12 passed in 3.1s ===",
    "test_stderr": "",
    "duration_seconds": 41.7,
    "completed_at": "2026-10-05T10:15:00Z",
    "original_failure_resolved": true
  }
}
```

`pr_opened`:

```json
{
  "incident_id": "3f2a9c1e-7b4d-4e8a-9f10-2c6d5e8b1a47",
  "event": "pr_opened",
  "pull_request": {
    "pr_number": 9,
    "pr_url": "https://github.com/phoenix-demo/orders-api/pull/9",
    "head_branch": "phoenix/fix/3f2a9c1e-7b4d-4e8a-9f10-2c6d5e8b1a47"
  }
}
```

Every event also accepts optional `at` (ISO-8601 time; defaults to now) and `message` (timeline text).

Demo run without the agent (stdlib only, API must be running): `python scripts/send_demo_events.py`
sends detected → diagnosing → fix_proposed → validating → validated → pr_opened for a new uuid,
2 seconds apart. Options: `--reject` (ends in a failed validation), `--delay 0.5`,
`--url http://127.0.0.1:8000/api/ingest/events`, `--token …` (default: `PHOENIX_INGEST_TOKEN`).

Environment variables:

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `DEMO_FIXTURES` | `1` | `0`/`false`/`no`/`off` hides `INC-001`…`INC-008` so only ingested incidents show. |
| `PHOENIX_DATA_FILE` | `phoenix-api/data/incidents.json` | Where ingested incidents are stored (git-ignored). |
| `PHOENIX_REPO` | `phoenix-demo/orders-api` | Repo for a new incident when its first event has no `repo`. |
| `PHOENIX_INGEST_TOKEN` | unset | When set, ingest requires a matching `X-Phoenix-Token` header. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed browser origins. |

## Tests

From `phoenix-api/`, with the venv active:

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The tests use a temporary incidents file and never write to `data/incidents.json`.
