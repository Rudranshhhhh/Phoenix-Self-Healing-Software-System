"""Fake incidents for the stub API.

INC-001..INC-007 hold one incident per status. INC-008 is "live": it is
rebuilt on every request from the seconds since the server started and
walks the happy path, one status every 5 seconds, then starts over.

Every incident goes through ``build_incident``, which is the only place
that decides which sections a status is allowed to have.
"""

from datetime import datetime, timedelta, timezone

from app.models import (
    Diagnosis,
    Incident,
    IncidentError,
    IncidentSource,
    IncidentStatus,
    Patch,
    PullRequest,
    StackFrame,
    TimelineEntry,
    Validation,
)

REPO = "phoenix-demo/orders-api"
GITHUB = f"https://github.com/{REPO}"

SERVER_STARTED = datetime.now(timezone.utc).replace(microsecond=0)

HAPPY_PATH: list[IncidentStatus] = [
    "detected", "diagnosing", "fix_proposed", "validating", "validated", "pr_opened",
]
REJECTED_PATH: list[IncidentStatus] = [
    "detected", "diagnosing", "fix_proposed", "validating", "rejected",
]

# Which optional sections each status has reached.
SECTIONS: dict[IncidentStatus, set[str]] = {
    "detected": set(),
    "diagnosing": set(),
    "fix_proposed": {"diagnosis", "patch"},
    "validating": {"diagnosis", "patch"},
    "validated": {"diagnosis", "patch", "validation"},
    "rejected": {"diagnosis", "patch", "validation"},
    "pr_opened": {"diagnosis", "patch", "validation", "pull_request"},
}

TIMELINE_MESSAGES: dict[IncidentStatus, str | None] = {
    "detected": None,  # set per incident: where it came from
    "diagnosing": "Collected stack trace and source context; asking the model for a root cause",
    "fix_proposed": "Patch generated",
    "validating": "Running the test suite and the reproduction in a sandbox",
    "validated": "Sandbox: tests pass and the original error no longer reproduces",
    "rejected": "Sandbox: patch failed validation",
    "pr_opened": "Pull request opened",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def path_to(status: IncidentStatus) -> list[IncidentStatus]:
    """Statuses an incident passed through to reach ``status``, in order."""
    path = REJECTED_PATH if status == "rejected" else HAPPY_PATH
    return path[: path.index(status) + 1]


def traceback_text(frames: list[StackFrame], exception_type: str, message: str) -> str:
    lines = ["Traceback (most recent call last):"]
    for f in frames:
        lines.append(f'  File "{f.file}", line {f.line}, in {f.function}')
        lines.append(f"    {f.code}")
    lines.append(f"{exception_type}: {message}")
    return "\n".join(lines)


def diff_text(raw: str) -> str:
    """Make a hand-written diff strict: a blank context line is a single space."""
    body = raw[:-1] if raw.endswith("\n") else raw  # keep trailing blank context lines
    return "\n".join(line or " " for line in body.split("\n")) + "\n"


def make_error(exception_type: str, message: str, frames: list[StackFrame]) -> IncidentError:
    return IncidentError(
        exception_type=exception_type,
        message=message,
        stack_trace=traceback_text(frames, exception_type, message),
        frames=frames,
    )


def pytest_output(
    files: list[tuple[str, str]],
    summary: str,
    failures: str = "",
    short_summary: str = "",
) -> str:
    """Render pytest-style output. ``files`` is (path, result chars like '..F.')."""
    total = sum(len(chars) for _, chars in files)
    lines = [
        " test session starts ".center(80, "="),
        "platform linux -- Python 3.12.6, pytest-8.3.3, pluggy-1.5.0",
        "rootdir: /sandbox/orders-api",
        "configfile: pyproject.toml",
        "plugins: anyio-4.6.0, cov-5.0.0",
        f"collected {total} items",
        "",
    ]
    done = 0
    for path, chars in files:
        done += len(chars)
        pct = f"[{round(done * 100 / total):>3}%]"
        lines.append(f"{path} {chars}".ljust(80 - len(pct)) + pct)
    lines.append("")
    if failures:
        lines.append(" FAILURES ".center(80, "="))
        lines.append(failures.rstrip("\n"))
    if short_summary:
        lines.append(" short test summary info ".center(80, "="))
        lines.append(short_summary)
    lines.append(f" {summary} ".center(80, "="))
    return "\n".join(lines)


def build_incident(
    *,
    id: str,
    status: IncidentStatus,
    source: IncidentSource,
    error: IncidentError,
    started_at: datetime,
    step: timedelta,
    detected_message: str,
    diagnosis: Diagnosis | None = None,
    patch: Patch | None = None,
    validation: dict | None = None,
    pull_request: PullRequest | None = None,
) -> Incident:
    """Assemble an incident, keeping only the sections ``status`` has reached.

    Sections the status has not reached are dropped; sections it has reached
    must be supplied. ``validation`` is the Validation fields minus
    ``finished_at``, which is taken from the timeline entry where validation
    finished.
    """
    reached = SECTIONS[status]
    supplied = {"diagnosis": diagnosis, "patch": patch, "validation": validation,
                "pull_request": pull_request}
    missing = [name for name in reached if supplied[name] is None]
    if missing:
        raise ValueError(f"{id}: status {status} needs {', '.join(sorted(missing))}")
    timeline = [
        TimelineEntry(
            status=s,
            at=started_at + i * step,
            message=detected_message if s == "detected" else TIMELINE_MESSAGES[s],
        )
        for i, s in enumerate(path_to(status))
    ]

    # Blame is the diagnosis' call; before there is one, no frame is blamed.
    if "diagnosis" not in reached:
        error = error.model_copy(
            update={"frames": [f.model_copy(update={"blame": False}) for f in error.frames]}
        )

    built_validation = None
    if "validation" in reached:
        finished = next(e.at for e in timeline if e.status in ("validated", "rejected"))
        built_validation = Validation(**validation, finished_at=finished)

    return Incident(
        id=id,
        repo=REPO,
        status=status,
        source=source,
        error=error,
        diagnosis=diagnosis if "diagnosis" in reached else None,
        patch=patch if "patch" in reached else None,
        validation=built_validation,
        pull_request=pull_request if "pull_request" in reached else None,
        fix_branch=pull_request.branch if "pull_request" in reached else None,
        timeline=timeline,
        created_at=timeline[0].at,
        updated_at=timeline[-1].at,
    )


def actions_source(run_id: int, sha: str) -> IncidentSource:
    return IncidentSource(
        type="github_actions",
        workflow_run_url=f"{GITHUB}/actions/runs/{run_id}",
        commit_sha=sha,
    )


def docker_source(container: str, sha: str) -> IncidentSource:
    return IncidentSource(type="docker_runtime", container=container, commit_sha=sha)


def ago(minutes: float) -> datetime:
    return SERVER_STARTED - timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# INC-001 · detected · KeyError in shipping label builder (GitHub Actions)
# ---------------------------------------------------------------------------

INC_001 = build_incident(
    id="INC-001",
    status="detected",
    source=actions_source(11873402561, "4e1d9a0"),
    error=make_error(
        "KeyError",
        "'shipping_address'",
        [
            StackFrame(file="tests/test_checkout.py", line=88, function="test_guest_checkout_creates_label",
                       code='response = client.post("/v2/checkout", json=guest_cart_payload())'),
            StackFrame(file="app/api/routes/checkout.py", line=41, function="post_checkout",
                       code="label = build_label(order, payload)"),
            StackFrame(file="app/services/shipping.py", line=19, function="build_label",
                       code='address = payload["shipping_address"]', blame=True),
        ],
    ),
    started_at=ago(3),
    step=timedelta(seconds=20),
    detected_message="CI run #11873402561 failed on main (tests/test_checkout.py)",
)


# ---------------------------------------------------------------------------
# INC-002 · diagnosing · AttributeError in receipt worker (Docker runtime)
# ---------------------------------------------------------------------------

INC_002 = build_incident(
    id="INC-002",
    status="diagnosing",
    source=docker_source("orders-api-worker-1", "4e1d9a0"),
    error=make_error(
        "AttributeError",
        "'NoneType' object has no attribute 'email'",
        [
            StackFrame(file="/usr/local/lib/python3.12/site-packages/celery/app/trace.py", line=453,
                       function="trace_task", code="R = retval = fun(*args, **kwargs)"),
            StackFrame(file="app/workers/notifications.py", line=34, function="send_receipt",
                       code="to=order.customer.email,"),
        ],
    ),
    started_at=ago(6),
    step=timedelta(seconds=15),
    detected_message="ERROR in container orders-api-worker-1 logs (task notifications.send_receipt)",
)


# ---------------------------------------------------------------------------
# INC-003 · fix_proposed · TypeError on flat-amount promos (GitHub Actions)
# Two files, three hunks.
# ---------------------------------------------------------------------------

INC_003_DIFF = diff_text("""\
--- a/app/services/pricing.py
+++ b/app/services/pricing.py
@@ -1,6 +1,6 @@
 from decimal import Decimal

-from app.models.promo import Promo
+from app.models.promo import DiscountKind, Promo


 def subtotal(cart) -> Decimal:
@@ -80,6 +80,10 @@ def subtotal(cart) -> Decimal:
 def price_after_discount(cart, promo: Promo | None) -> Decimal:
     subtotal_ = subtotal(cart)
     if promo is None:
         return subtotal_
-    return subtotal_ - (subtotal_ * promo.percent / 100)
+    if promo.kind is DiscountKind.FLAT:
+        discounted = subtotal_ - promo.amount
+    else:
+        discounted = subtotal_ - (subtotal_ * promo.percent / 100)
+    return max(discounted, Decimal("0"))

--- a/tests/test_pricing.py
+++ b/tests/test_pricing.py
@@ -1,4 +1,5 @@
 from decimal import Decimal

+from app.models.promo import DiscountKind
 from app.services.pricing import price_after_discount
 from tests.factories import cart_of, make_promo
@@ -40,3 +41,12 @@ def test_percent_promo():
     promo = make_promo(percent=10)
     assert price_after_discount(cart_of(100), promo) == Decimal("90")

+
+def test_flat_promo():
+    promo = make_promo(kind=DiscountKind.FLAT, amount=Decimal("15"), percent=None)
+    assert price_after_discount(cart_of(100), promo) == Decimal("85")
+
+
+def test_flat_promo_never_negative():
+    promo = make_promo(kind=DiscountKind.FLAT, amount=Decimal("500"), percent=None)
+    assert price_after_discount(cart_of(100), promo) == Decimal("0")
""")

INC_003 = build_incident(
    id="INC-003",
    status="fix_proposed",
    source=actions_source(11873119044, "b72c5f3"),
    error=make_error(
        "TypeError",
        "unsupported operand type(s) for *: 'decimal.Decimal' and 'NoneType'",
        [
            StackFrame(file="tests/test_checkout.py", line=132, function="test_checkout_with_flat_promo",
                       code='response = client.post("/v2/checkout", json=cart_payload(promo="SPRING15"))'),
            StackFrame(file="app/api/routes/checkout.py", line=61, function="post_checkout",
                       code="total = price_after_discount(cart, promo)"),
            StackFrame(file="app/services/pricing.py", line=84, function="price_after_discount",
                       code="return subtotal_ - (subtotal_ * promo.percent / 100)", blame=True),
        ],
    ),
    started_at=ago(11),
    step=timedelta(seconds=40),
    detected_message="CI run #11873119044 failed on main (tests/test_checkout.py)",
    diagnosis=Diagnosis(
        root_cause="promo.percent is None for flat-amount promos, so the percentage formula multiplies by None.",
        explanation=(
            "Promos created with kind=FLAT store the discount in promo.amount and leave percent null. "
            "price_after_discount assumes every promo is a percentage. The fix branches on promo.kind "
            "and floors the result at zero so a large flat promo cannot produce a negative total."
        ),
        suspect_file="app/services/pricing.py",
        suspect_line=84,
        confidence=0.92,
        context_files=["app/services/pricing.py", "app/models/promo.py", "tests/test_pricing.py"],
    ),
    patch=Patch(
        summary="Handle flat-amount promos in price_after_discount",
        diff=INC_003_DIFF,
        files_changed=["app/services/pricing.py", "tests/test_pricing.py"],
    ),
)


# ---------------------------------------------------------------------------
# INC-004 · validating · ValueError on empty ?page= (Docker runtime)
# ---------------------------------------------------------------------------

INC_004_DIFF = diff_text("""\
--- a/app/api/pagination.py
+++ b/app/api/pagination.py
@@ -9,4 +9,7 @@ DEFAULT_PAGE = 1
 def parse_page(raw: str | None) -> int:
     if raw is None:
         return DEFAULT_PAGE
-    return max(1, int(raw))
+    try:
+        return max(1, int(raw))
+    except ValueError:
+        return DEFAULT_PAGE
""")

INC_004 = build_incident(
    id="INC-004",
    status="validating",
    source=docker_source("orders-api-web-1", "b72c5f3"),
    error=make_error(
        "ValueError",
        "invalid literal for int() with base 10: ''",
        [
            StackFrame(file="/usr/local/lib/python3.12/site-packages/starlette/routing.py", line=73,
                       function="app", code="response = await f(request)"),
            StackFrame(file="app/api/routes/orders.py", line=27, function="list_orders",
                       code='page = parse_page(request.query_params.get("page"))'),
            StackFrame(file="app/api/pagination.py", line=12, function="parse_page",
                       code="return max(1, int(raw))", blame=True),
        ],
    ),
    started_at=ago(18),
    step=timedelta(seconds=45),
    detected_message="ERROR in container orders-api-web-1 logs (GET /orders?page=)",
    diagnosis=Diagnosis(
        root_cause="An empty ?page= query parameter is passed straight to int().",
        explanation=(
            "parse_page only guards against a missing parameter, not an empty or non-numeric one. "
            "Falling back to the default page matches how the rest of the API treats bad paging input."
        ),
        suspect_file="app/api/pagination.py",
        suspect_line=12,
        confidence=0.88,
        context_files=["app/api/pagination.py", "app/api/routes/orders.py"],
    ),
    patch=Patch(
        summary="Fall back to page 1 when ?page= is empty or not a number",
        diff=INC_004_DIFF,
        files_changed=["app/api/pagination.py"],
    ),
)


# ---------------------------------------------------------------------------
# INC-005 · validated · ZeroDivisionError on a day with no orders (GitHub Actions)
# ---------------------------------------------------------------------------

INC_005_DIFF = diff_text("""\
--- a/app/services/reports.py
+++ b/app/services/reports.py
@@ -30,5 +30,6 @@ from decimal import Decimal

 def average_order_value(orders: list[Order]) -> Decimal:
     total = sum((o.total for o in orders), Decimal("0"))
-    return total / len(orders)
+    count = len(orders)
+    return total / count if count else Decimal("0")

""")

INC_005 = build_incident(
    id="INC-005",
    status="validated",
    source=actions_source(11872650318, "9a0e7c1"),
    error=make_error(
        "ZeroDivisionError",
        "division by zero",
        [
            StackFrame(file="tests/test_reports.py", line=54, function="test_daily_report_with_no_orders",
                       code='report = client.get("/reports/daily", params={"date": "2026-01-01"}).json()'),
            StackFrame(file="app/api/routes/reports.py", line=18, function="get_daily_report",
                       code='"aov": average_order_value(orders),'),
            StackFrame(file="app/services/reports.py", line=33, function="average_order_value",
                       code="return total / len(orders)", blame=True),
        ],
    ),
    started_at=ago(42),
    step=timedelta(seconds=50),
    detected_message="CI run #11872650318 failed on main (tests/test_reports.py)",
    diagnosis=Diagnosis(
        root_cause="average_order_value divides by len(orders) without handling an empty list.",
        explanation=(
            "The daily report is requested for dates with no orders (new stores, holidays). "
            "An empty day should report an average of zero rather than crash the endpoint."
        ),
        suspect_file="app/services/reports.py",
        suspect_line=33,
        confidence=0.95,
        context_files=["app/services/reports.py", "app/api/routes/reports.py"],
    ),
    patch=Patch(
        summary="Return zero average order value for days with no orders",
        diff=INC_005_DIFF,
        files_changed=["app/services/reports.py"],
    ),
    validation=dict(
        environment="docker",
        result="PASS",
        tests_run=61,
        tests_passed=61,
        bug_reproduced_before_patch=True,
        bug_reproduces_after_patch=False,
        duration_seconds=19.4,
        output=pytest_output(
            [
                ("tests/test_checkout.py", ".........."),
                ("tests/test_inventory.py", "............"),
                ("tests/test_orders.py", "..............."),
                ("tests/test_pricing.py", "........"),
                ("tests/test_reports.py", ".........."),
                ("tests/test_shipping.py", "......"),
            ],
            "61 passed in 12.84s",
        ),
    ),
)


# ---------------------------------------------------------------------------
# INC-006 · rejected · IndexError when every batch is reserved (GitHub Actions)
# ---------------------------------------------------------------------------

INC_006_DIFF = diff_text("""\
--- a/app/services/inventory.py
+++ b/app/services/inventory.py
@@ -44,6 +44,6 @@ def available_batches(sku: str, include_reserved: bool = False) -> list[Batch]:
 def reserve_stock(sku: str, quantity: int) -> Reservation:
-    batches = available_batches(sku)
+    batches = available_batches(sku) or available_batches(sku, include_reserved=True)
     batches.sort(key=lambda b: b.expires_at)
     next_batch = batches[0]
     if next_batch.quantity < quantity:
         raise InsufficientStock(sku, quantity)
""")

INC_006_FAILURE = """\
_________________ test_reserve_stock_when_all_batches_reserved _________________

db = <sqlalchemy.orm.session.Session object at 0x7f3a1c2b9d50>

    def test_reserve_stock_when_all_batches_reserved(db):
        sku = make_sku(db, batches=[make_batch(reserved=True)])
>       reserve_stock(sku.code, quantity=1)

tests/test_inventory.py:112:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
app/services/inventory.py:47: in reserve_stock
    next_batch = batches[0]
E   IndexError: list index out of range
"""

INC_006 = build_incident(
    id="INC-006",
    status="rejected",
    source=actions_source(11871987745, "9a0e7c1"),
    error=make_error(
        "IndexError",
        "list index out of range",
        [
            StackFrame(file="app/workers/fulfillment.py", line=63, function="handle_order",
                       code="reservation = reserve_stock(order.sku, order.quantity)"),
            StackFrame(file="app/services/inventory.py", line=47, function="reserve_stock",
                       code="next_batch = batches[0]", blame=True),
        ],
    ),
    started_at=ago(75),
    step=timedelta(seconds=55),
    detected_message="CI run #11871987745 failed on main (tests/test_inventory.py)",
    diagnosis=Diagnosis(
        root_cause="reserve_stock assumes at least one unreserved batch exists for the SKU.",
        explanation=(
            "When every batch of a SKU is already reserved, available_batches returns an empty list "
            "and batches[0] raises. The patch retries with reserved batches included."
        ),
        suspect_file="app/services/inventory.py",
        suspect_line=47,
        confidence=0.58,
        context_files=["app/services/inventory.py", "app/workers/fulfillment.py"],
    ),
    patch=Patch(
        summary="Fall back to reserved batches when no free batch is available",
        diff=INC_006_DIFF,
        files_changed=["app/services/inventory.py"],
    ),
    validation=dict(
        environment="docker",
        result="FAIL",
        tests_run=58,
        tests_passed=57,
        bug_reproduced_before_patch=True,
        bug_reproduces_after_patch=True,
        duration_seconds=21.7,
        output=pytest_output(
            [
                ("tests/test_checkout.py", ".........."),
                ("tests/test_inventory.py", "..........F"),
                ("tests/test_orders.py", "..............."),
                ("tests/test_pricing.py", "......"),
                ("tests/test_reports.py", "........"),
                ("tests/test_shipping.py", "........"),
            ],
            "1 failed, 57 passed in 14.02s",
            failures=INC_006_FAILURE,
            short_summary=(
                "FAILED tests/test_inventory.py::test_reserve_stock_when_all_batches_reserved"
                " - IndexError: list index out of range"
            ),
        ),
        rejection_reason=(
            "The original IndexError still reproduces: available_batches(sku, include_reserved=True) "
            "also returns an empty list when every batch is reserved, so batches[0] still fails. "
            "The SKU should raise InsufficientStock instead."
        ),
    ),
)


# ---------------------------------------------------------------------------
# INC-007 · pr_opened · naive vs aware datetime comparison (GitHub Actions)
# Two files, three hunks.
# ---------------------------------------------------------------------------

INC_007_DIFF = diff_text("""\
--- a/app/services/coupons.py
+++ b/app/services/coupons.py
@@ -1,7 +1,8 @@
 from datetime import datetime, timezone

 from app.db import session
 from app.models.coupon import Coupon
+from app.utils.time import as_utc


 class CouponExpired(Exception):
@@ -19,7 +20,7 @@ def validate_coupon(code: str) -> Coupon:
     coupon = session.get(Coupon, code)
     if coupon is None:
         raise CouponNotFound(code)
-    if coupon.expires_at < datetime.now(timezone.utc):
+    if as_utc(coupon.expires_at) < datetime.now(timezone.utc):
         raise CouponExpired(code)
     return coupon

--- a/app/utils/time.py
+++ b/app/utils/time.py
@@ -3,3 +3,10 @@

 def utcnow() -> datetime:
     return datetime.now(timezone.utc)
+
+
+def as_utc(value: datetime) -> datetime:
+    \"\"\"Treat naive datetimes loaded from the database as UTC.\"\"\"
+    if value.tzinfo is None:
+        return value.replace(tzinfo=timezone.utc)
+    return value
""")

INC_007 = build_incident(
    id="INC-007",
    status="pr_opened",
    source=actions_source(11870533902, "e5d01b8"),
    error=make_error(
        "TypeError",
        "can't compare offset-naive and offset-aware datetimes",
        [
            StackFrame(file="tests/test_coupons.py", line=29, function="test_expired_coupon_is_rejected",
                       code='response = client.post("/v2/checkout/coupon", json={"code": "OLD10"})'),
            StackFrame(file="app/api/routes/checkout.py", line=54, function="apply_coupon_route",
                       code="coupon = validate_coupon(body.code)"),
            StackFrame(file="app/services/coupons.py", line=22, function="validate_coupon",
                       code="if coupon.expires_at < datetime.now(timezone.utc):", blame=True),
        ],
    ),
    started_at=ago(140),
    step=timedelta(minutes=1),
    detected_message="CI run #11870533902 failed on main (tests/test_coupons.py)",
    diagnosis=Diagnosis(
        root_cause="coupon.expires_at is loaded as a naive datetime and compared with an aware one.",
        explanation=(
            "The expires_at column is 'timestamp without time zone', so SQLAlchemy returns naive "
            "datetimes. validate_coupon compares it with datetime.now(timezone.utc), which Python "
            "refuses. Values are written in UTC, so treating naive values as UTC is safe."
        ),
        suspect_file="app/services/coupons.py",
        suspect_line=22,
        confidence=0.9,
        context_files=["app/services/coupons.py", "app/models/coupon.py", "app/utils/time.py"],
    ),
    patch=Patch(
        summary="Normalise coupon expiry to UTC before comparing",
        diff=INC_007_DIFF,
        files_changed=["app/services/coupons.py", "app/utils/time.py"],
    ),
    validation=dict(
        environment="docker",
        result="PASS",
        tests_run=64,
        tests_passed=64,
        bug_reproduced_before_patch=True,
        bug_reproduces_after_patch=False,
        duration_seconds=22.3,
        output=pytest_output(
            [
                ("tests/test_checkout.py", ".........."),
                ("tests/test_coupons.py", "......"),
                ("tests/test_inventory.py", "............"),
                ("tests/test_orders.py", "..............."),
                ("tests/test_pricing.py", "......."),
                ("tests/test_reports.py", "........"),
                ("tests/test_shipping.py", "......"),
            ],
            "64 passed in 13.37s",
        ),
    ),
    pull_request=PullRequest(
        number=7,
        url=f"{GITHUB}/pull/7",
        branch="phoenix/fix/INC-007",
        state="open",
    ),
)


STATIC_INCIDENTS: list[Incident] = [INC_001, INC_002, INC_003, INC_004, INC_005, INC_006, INC_007]


# ---------------------------------------------------------------------------
# INC-008 · live · advances one status every 5 seconds, then starts over
# ---------------------------------------------------------------------------

LIVE_STEP_SECONDS = 5
LIVE_CYCLE_SECONDS = LIVE_STEP_SECONDS * len(HAPPY_PATH)

INC_008_DIFF = diff_text("""\
--- a/app/services/orders.py
+++ b/app/services/orders.py
@@ -71,6 +71,8 @@ def create_order(payload: OrderIn) -> Order:
 def line_total(item: dict) -> Decimal:
-    sku = item["sku"]
-    price = catalog.price_of(sku)
+    sku = item.get("sku") or item.get("product_sku")
+    if sku is None:
+        raise InvalidLineItem("line item has no sku")
+    price = catalog.price_of(sku)
     return price * item["quantity"]


""")


def live_incident(seconds_since_start: float) -> Incident:
    """INC-008 as it looks ``seconds_since_start`` seconds after the server started."""
    elapsed = max(0.0, seconds_since_start)
    cycle = int(elapsed // LIVE_CYCLE_SECONDS)
    index = int((elapsed % LIVE_CYCLE_SECONDS) // LIVE_STEP_SECONDS)
    cycle_started = SERVER_STARTED + timedelta(seconds=cycle * LIVE_CYCLE_SECONDS)

    return build_incident(
        id="INC-008",
        status=HAPPY_PATH[index],
        source=actions_source(11874000000 + cycle, "c3f9e21"),
        error=make_error(
            "KeyError",
            "'sku'",
            [
                StackFrame(file="tests/test_orders.py", line=77, function="test_create_order_from_mobile_client",
                           code='response = client.post("/orders", json=mobile_order_payload())'),
                StackFrame(file="app/services/orders.py", line=66, function="create_order",
                           code="total = sum(line_total(item) for item in payload.items)"),
                StackFrame(file="app/services/orders.py", line=72, function="line_total",
                           code='sku = item["sku"]', blame=True),
            ],
        ),
        started_at=cycle_started,
        step=timedelta(seconds=LIVE_STEP_SECONDS),
        detected_message=f"CI run #{11874000000 + cycle} failed on main (tests/test_orders.py)",
        diagnosis=Diagnosis(
            root_cause="The mobile client sends line items with 'product_sku' instead of 'sku'.",
            explanation=(
                "Mobile app 4.2 renamed the field. line_total indexes item['sku'] directly, so the "
                "request fails before validation. The patch accepts both names and raises a clear "
                "InvalidLineItem error when neither is present."
            ),
            suspect_file="app/services/orders.py",
            suspect_line=72,
            confidence=0.87,
            context_files=["app/services/orders.py", "app/schemas/order.py"],
        ),
        patch=Patch(
            summary="Accept 'product_sku' as an alias for 'sku' in order line items",
            diff=INC_008_DIFF,
            files_changed=["app/services/orders.py"],
        ),
        validation=dict(
            environment="docker",
            result="PASS",
            tests_run=62,
            tests_passed=62,
            bug_reproduced_before_patch=True,
            bug_reproduces_after_patch=False,
            duration_seconds=4.1,
            output=pytest_output(
                [
                    ("tests/test_checkout.py", ".........."),
                    ("tests/test_inventory.py", "............"),
                    ("tests/test_orders.py", "................."),
                    ("tests/test_pricing.py", "......."),
                    ("tests/test_reports.py", "........"),
                    ("tests/test_shipping.py", "........"),
                ],
                "62 passed in 3.88s",
            ),
        ),
        pull_request=PullRequest(
            number=8,
            url=f"{GITHUB}/pull/8",
            branch="phoenix/fix/INC-008",
            state="open",
        ),
    )
