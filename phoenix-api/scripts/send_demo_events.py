"""Send a realistic sequence of pipeline events to phoenix-api, like the agent would.

Usage (from phoenix-api/, with the API running):
    python scripts/send_demo_events.py [--url URL] [--token TOKEN] [--delay 2] [--reject]

Stdlib only. Each run uses a fresh uuid, so it shows up as a new dashboard incident.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_URL = "http://127.0.0.1:8000/api/ingest/events"

TRACEBACK = """Traceback (most recent call last):
  File "/app/app/routes/orders.py", line 58, in create_order
    order = checkout(payload)
  File "/app/app/checkout.py", line 31, in checkout
    total = cart_total(cart["items"])
  File "/app/app/pricing.py", line 17, in cart_total
    return sum(item["price"] * item["qty"] for item in items)
KeyError: 'price'"""

OLD_CODE = '''def cart_total(items):
    # Sum line totals for every item in the cart.
    return sum(item["price"] * item["qty"] for item in items)'''

NEW_CODE = '''def cart_total(items):
    # Sum line totals for every item in the cart.
    return sum(item.get("price", item.get("unit_price", 0)) * item["qty"] for item in items)'''

PASS_OUTPUT = """============================= test session starts =============================
collected 18 items

tests/test_pricing.py ........                                           [ 44%]
tests/test_checkout.py ..........                                        [100%]

============================= 18 passed in 4.2s ============================="""

FAIL_OUTPUT = """============================= test session starts =============================
collected 18 items

tests/test_pricing.py ......F.                                           [ 44%]
tests/test_checkout.py ........F.                                        [100%]

=================================== FAILURES ===================================
____________________________ test_total_with_discount ____________________________
E   AssertionError: assert 90.0 == 81.0
____________________________ test_checkout_legacy_cart ___________________________
E   KeyError: 'qty'
=========================== short test summary info ============================
FAILED tests/test_pricing.py::test_total_with_discount
FAILED tests/test_checkout.py::test_checkout_legacy_cart
========================= 2 failed, 16 passed in 4.0s ========================="""


def build_events(incident_id: str, reject: bool) -> list[dict]:
    events: list[dict] = [
        {
            "incident_id": incident_id,
            "event": "detected",
            "message": "KeyError in the orders-api container",
            "source": {"type": "docker_runtime", "container": "orders-api"},
            "error": {"exception_type": "KeyError", "message": "'price'", "stack_trace": TRACEBACK},
        },
        {
            "incident_id": incident_id,
            "event": "diagnosing",
            "message": "Reading the traceback and app/pricing.py",
        },
        {
            "incident_id": incident_id,
            "event": "fix_proposed",
            "diagnosis": {
                "root_cause": 'cart_total reads item["price"], but items from the legacy cart only have "unit_price".',
                "explanation": (
                    "Orders created before the pricing migration store the price under unit_price. "
                    "cart_total indexes item[\"price\"] directly, so any legacy cart raises KeyError "
                    "and the order request fails with a 500."
                ),
                "affected_file": "app/pricing.py",
                "affected_line": 17,
                "confidence": 0.82,
            },
            "patch": {
                "explanation": "Fall back to unit_price when an item has no price.",
                "patches": [{"file": "app/pricing.py", "old_code": OLD_CODE, "new_code": NEW_CODE}],
            },
        },
        {
            "incident_id": incident_id,
            "event": "validating",
        },
    ]
    if reject:
        events.append(
            {
                "incident_id": incident_id,
                "event": "rejected",
                "validation": {
                    "validated": False,
                    "reason": "Patch rejected — tests failed",
                    "test_stdout": FAIL_OUTPUT,
                    "duration_seconds": 29.8,
                    "original_failure_resolved": True,
                },
            }
        )
    else:
        events += [
            {
                "incident_id": incident_id,
                "event": "validated",
                "validation": {
                    "validated": True,
                    "reason": "All validation checks passed.",
                    "test_stdout": PASS_OUTPUT,
                    "duration_seconds": 31.5,
                    "original_failure_resolved": True,
                },
            },
            {
                "incident_id": incident_id,
                "event": "pr_opened",
                "pull_request": {
                    "pr_number": None,
                    "pr_url": "https://github.com/phoenix-demo/orders-api/pull/12",
                    "head_branch": f"phoenix/fix/{incident_id}",
                },
            },
        ]
    return events


def post(url: str, token: str | None, payload: dict) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Phoenix-Token"] = token
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"detail": body.decode("utf-8", "replace")}


def main() -> int:
    parser = argparse.ArgumentParser(description="POST a demo pipeline run to phoenix-api.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"ingest URL (default {DEFAULT_URL})")
    parser.add_argument("--token", default=os.environ.get("PHOENIX_INGEST_TOKEN"),
                        help="X-Phoenix-Token value (default: env PHOENIX_INGEST_TOKEN)")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between events (default 2)")
    parser.add_argument("--reject", action="store_true", help="end with a failed validation instead of a PR")
    args = parser.parse_args()

    incident_id = str(uuid.uuid4())
    print(f"agent incident id: {incident_id}")
    events = build_events(incident_id, args.reject)

    for i, event in enumerate(events):
        if i:
            time.sleep(args.delay)
        try:
            status, body = post(args.url, args.token, event)
        except urllib.error.URLError as exc:
            print(f"{event['event']:<13} -> cannot reach {args.url}: {exc.reason}")
            return 1
        if status != 200:
            print(f"{event['event']:<13} -> HTTP {status}: {body.get('detail')}")
            return 1
        print(f"{event['event']:<13} -> HTTP {status}  {body['id']}  status={body['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
