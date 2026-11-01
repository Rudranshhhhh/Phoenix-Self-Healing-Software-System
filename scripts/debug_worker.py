"""Debug: show exactly what evidence the worker builds for a portfolio incident."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "phoenix-api"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import requests

API = os.environ["PHOENIX_API_URL"]
TOKEN = os.environ["PHOENIX_AGENT_TOKEN"]

# Get the latest portfolio incident
r = requests.get(f"{API}/api/incidents?page_size=10", timeout=10)
incidents = r.json().get("incidents", [])
portfolio = [i for i in incidents if "portfolio" in (i.get("repository") or "")]
if not portfolio:
    print("No portfolio incidents found")
    sys.exit(1)

inc = portfolio[0]
print(f"Incident: {inc['incident_id']} | status={inc['status']}")
print(f"Repository: {inc['repository']}")
print(f"Commit: {inc.get('commit','')[:12]}")
print(f"Branch: {inc.get('branch')}")
print()
payload = inc.get("payload", {})
logs = payload.get("logs", "")
print(f"Logs length: {len(logs)} chars")
print(f"Logs first 500 chars:\n{logs[:500]}")
print()

# Now simulate evidence extraction
from app.evidence import extract_evidence_from_ci_payload, _parse_ci_logs
error_type, error_message, file_hint, line_hint = _parse_ci_logs(logs, payload.get("stage",""))
print(f"Parsed: error_type={error_type!r}")
print(f"        error_message={error_message!r}")
print(f"        file_hint={file_hint!r}")
print(f"        line_hint={line_hint!r}")
