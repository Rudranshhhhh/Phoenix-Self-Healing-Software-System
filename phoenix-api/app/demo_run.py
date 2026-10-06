"""Simulated run: replays the real INC-109 pipeline run (demo/broken_app) through ingest.

POST /api/demo/run calls start(). No Docker, no LLM: the events carry fixed
data and go through the same IncidentStore.apply the ingest route uses, so
the incident looks and behaves like a real one, apart from simulated=True.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from . import ingest
from .ingest import IngestEvent

log = logging.getLogger(__name__)

# Seconds after "detected" at which each later event is ingested.
DELAYS: list[tuple[float, str]] = [(2, "diagnosing"), (5, "fix_proposed"), (8, "validating"), (12, "validated")]

REPO = "phoenix-demo/orders-api"
CONTAINER = "phoenix-run-broken_app"

TRACEBACK = """Traceback (most recent call last):
  File "/app/app.py", line 15, in <module>
    print(get_product("apple"), flush=True)
  File "/app/app.py", line 9, in get_product
    return product["price"]
KeyError: 'price'"""

TEST_STDOUT = """============================= test session starts ==============================
cachedir: .pytest_cache
rootdir: /app
collecting ... collected 1 item

test_app.py::test_get_product_apple_does_not_raise PASSED                [100%]

============================== 1 passed in 2.45s ==============================="""

_running_id: Optional[str] = None
_task: Optional[asyncio.Task] = None


def running_id() -> Optional[str]:
    """Dashboard id of the simulated run in progress, if any."""
    return _running_id


def _payload(agent_id: str, event: str, incident_id: str) -> dict:
    base: dict = {"incident_id": agent_id, "event": event}
    if event == "detected":
        return {
            **base,
            "message": f"Simulated run: KeyError in the {CONTAINER} container",
            "repo": REPO,
            "simulated": True,
            "source": {"type": "docker_runtime", "container": CONTAINER},
            "error": {"exception_type": "KeyError", "message": "'price'", "stack_trace": TRACEBACK},
        }
    if event == "diagnosing":
        return {**base, "message": "Reading the traceback and app.py"}
    if event == "fix_proposed":
        return {
            **base,
            "diagnosis": {
                "root_cause": 'get_product() reads product["price"], but products only have a "cost" field.',
                "explanation": (
                    "PRODUCTS defines each product with a 'cost' field, but get_product() looks up "
                    "product[\"price\"], so Python raises KeyError when get_product('apple') is called."
                ),
                "affected_file": "app.py",
                "affected_line": 9,
                "confidence": 0.99,
            },
            "patch": {
                "explanation": "Return the existing 'cost' key instead of the missing 'price' key.",
                "patches": [
                    {
                        "file": "app.py",
                        "start_line": 9,
                        "old_code": '    return product["price"]',
                        "new_code": '    return product["cost"]',
                    }
                ],
            },
        }
    if event == "validating":
        return {**base, "environment": "local"}
    if event == "validated":
        return {
            **base,
            "branch": f"phoenix/fix/{incident_id}",
            "validation": {
                "validated": True,
                "reason": "All validation checks passed.",
                "test_stdout": TEST_STDOUT,
                "duration_seconds": 2.4,
                "original_failure_resolved": True,
                "environment": "local",
            },
        }
    raise ValueError(f"no simulated payload for {event!r}")


def _ingest(payload: dict):
    return ingest.store.apply(IngestEvent.model_validate(payload))


def start() -> str:
    """Clears old simulated incidents, ingests "detected" now and schedules the rest.

    Must be called from the running event loop (the async route). Returns the INC id.
    """
    global _running_id, _task
    ingest.store.remove_simulated()
    agent_id = str(uuid.uuid4())
    incident = _ingest(_payload(agent_id, "detected", ""))
    _running_id = incident.id
    _task = asyncio.get_running_loop().create_task(_replay(agent_id, incident.id))
    return incident.id


async def _replay(agent_id: str, incident_id: str) -> None:
    global _running_id, _task
    elapsed = 0.0
    try:
        for at, event in DELAYS:
            await asyncio.sleep(max(0.0, at - elapsed))
            elapsed = at
            _ingest(_payload(agent_id, event, incident_id))
    except Exception:
        log.exception("simulated run %s failed", incident_id)
        try:
            _ingest({"incident_id": agent_id, "event": "failed", "message": "Simulated run stopped with an error"})
        except Exception:
            log.exception("could not mark simulated run %s as failed", incident_id)
    finally:
        _running_id = None
        _task = None
