"""Update INC-021 to pr_opened with the PR URL."""
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

db = get_database()
result = db.incidents.find_one_and_update(
    {"incident_id": "INC-021"},
    {
        "$set": {
            "status": "pr_opened",
            "pr_url": "https://github.com/Rudranshhhhh/Rudransh-portfolio/pull/1",
            "pr_number": 1,
            "git_branch": "phoenix/fix/INC-021",
            "agent_worker_id": None,
            "lease_expires_at": None,
            "updated_at": datetime.now(timezone.utc),
        },
        "$push": {
            "timeline": {
                "status": "pr_opened",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "PR opened: https://github.com/Rudranshhhhh/Rudransh-portfolio/pull/1",
            }
        },
    },
    return_document=True,
)
if result:
    print("SUCCESS")
    print("INC-021 status:", result.get("status"))
    print("PR URL:", result.get("pr_url"))
else:
    print("NOT FOUND")
