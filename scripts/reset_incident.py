"""Force-reset an incident to queued_for_agent with zero attempts."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "phoenix-api"))
os.environ.setdefault("PHOENIX_WEBHOOK_SECRET", "6f16037529213d8ed1906ca9fa8eb825c975aac42b83ac274e84204e9937eeac")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
from unittest.mock import MagicMock
for m in ["agent","agent.ai","agent.ai.llm_engine","agent.ai.llm_engine.diagnosis","agent.sandbox","agent.sandbox.models"]:
    sys.modules[m] = MagicMock()
from app.database import init_database; init_database()
from app.database import get_database
from datetime import datetime, timezone

incident_id = sys.argv[1] if len(sys.argv) > 1 else "INC-017"
db = get_database()
result = db.incidents.find_one_and_update(
    {"incident_id": incident_id},
    {
        "$set": {
            "status": "queued_for_agent",
            "agent_worker_id": None,
            "lease_expires_at": None,
            "agent_attempts": 0,
            "updated_at": datetime.now(timezone.utc),
        },
        "$push": {
            "timeline": {
                "status": "queued_for_agent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Force-reset for clean retry",
            }
        },
    },
    return_document=True,
)
if result:
    print(f"Reset {incident_id}: status={result['status']} attempts={result.get('agent_attempts',0)}")
else:
    print(f"Incident {incident_id} not found")
