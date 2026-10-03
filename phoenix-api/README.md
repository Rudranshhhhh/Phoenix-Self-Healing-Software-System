# phoenix-api (stub)

A FastAPI stub that serves fake incidents so the dashboard can be built against real HTTP.
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

Fixtures: `INC-001`…`INC-007` are one incident per status. `INC-008` is live: it advances one
status every 5 seconds (detected → diagnosing → fix_proposed → validating → validated → pr_opened)
and then starts over. Its clock restarts whenever the server (or `--reload`) restarts.
