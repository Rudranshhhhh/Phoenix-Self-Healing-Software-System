// ---------------------------------------------------------------------------
// Stand-in for GET /api/incidents.
//
// Every traceback, frame and hunk here is written to be the kind of thing a
// real Python service actually throws — the UI is only as convincing as the
// data it renders, and the diff view has to survive real-world line lengths.
// ---------------------------------------------------------------------------

import type { Incident } from "../types/phoenix";

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();

/**
 * The incident used as the home page's hero. A promo row with a flat discount
 * leaves `percent` null, and the pricing path assumes it never is.
 */
export const HERO_INCIDENT: Incident = {
  id: "PHX-2291",
  service: "checkout-api",
  exception: "TypeError",
  message: "unsupported operand type(s) for *: 'Decimal' and 'NoneType'",
  severity: "critical",
  count: 68,
  usersAffected: 41,
  firstSeen: minutesAgo(14),
  lastSeen: minutesAgo(1),
  stage: "awaiting_review",
  request: {
    method: "POST",
    path: "/v2/checkout",
    status: 500,
    userAgent: "storefront-web/3.11.0",
    releaseSha: "9c41ab7",
  },
  frames: [
    {
      file: "app/api/routes/checkout.py",
      line: 61,
      fn: "post_checkout",
      code: "total = price_after_discount(cart, promo)",
    },
    {
      file: "app/services/pricing.py",
      line: 84,
      fn: "price_after_discount",
      code: "return subtotal - (subtotal * promo.percent / 100)",
      blame: true,
    },
  ],
  fix: {
    summary: "Handle flat-amount promos in price_after_discount",
    reasoning:
      "promo.percent is null for the 12 promo rows created with a flat discount, so the multiply raises before any validation runs. The patch branches on the discount kind instead of assuming a percentage, and floors the total at zero so a large flat promo can't produce a negative charge.",
    branch: "phoenix/fix-flat-promo-typeerror",
    testsRun: 214,
    testsPassed: 214,
    hunks: [
      {
        file: "app/services/pricing.py",
        startLine: 82,
        removed: ["    return subtotal - (subtotal * promo.percent / 100)"],
        added: [
          "    if promo.percent is None:",
          '        return max(Decimal("0"), subtotal - promo.flat_amount)',
          "    return subtotal - (subtotal * promo.percent / 100)",
        ],
      },
    ],
  },
};

export const MOCK_INCIDENTS: Incident[] = [
  HERO_INCIDENT,
  {
    id: "PHX-2288",
    service: "checkout-api",
    exception: "KeyError",
    message: "'shipping_address'",
    severity: "high",
    count: 23,
    usersAffected: 23,
    firstSeen: minutesAgo(51),
    lastSeen: minutesAgo(4),
    stage: "open",
    request: {
      method: "POST",
      path: "/v2/webhooks/carrier",
      status: 500,
      userAgent: "shipd-webhooks/1.4",
      releaseSha: "9c41ab7",
    },
    frames: [
      {
        file: "app/api/routes/webhooks.py",
        line: 118,
        fn: "carrier_callback",
        code: "address = payload[\"order\"][\"shipping_address\"]",
        blame: true,
      },
    ],
  },
  {
    id: "PHX-2284",
    service: "invoice-worker",
    exception: "AttributeError",
    message: "'NoneType' object has no attribute 'strip'",
    severity: "medium",
    count: 9,
    usersAffected: 0,
    firstSeen: minutesAgo(186),
    lastSeen: minutesAgo(64),
    stage: "pr_open",
    request: {
      method: "TASK",
      path: "invoices.render_pdf",
      status: 0,
      userAgent: "celery/5.4.0",
      releaseSha: "4f0d221",
    },
    frames: [
      {
        file: "app/workers/invoices.py",
        line: 203,
        fn: "render_pdf",
        code: "company = customer.legal_name.strip()",
        blame: true,
      },
    ],
    fix: {
      summary: "Fall back to display name when legal_name is unset",
      reasoning:
        "Customers imported before the 2024 schema change have a null legal_name. The PDF renderer is the only caller that assumes it is present.",
      branch: "phoenix/fix-invoice-legal-name",
      testsRun: 214,
      testsPassed: 214,
      prNumber: 482,
      hunks: [
        {
          file: "app/workers/invoices.py",
          startLine: 201,
          removed: ["    company = customer.legal_name.strip()"],
          added: ["    company = (customer.legal_name or customer.display_name).strip()"],
        },
      ],
    },
  },
  {
    id: "PHX-2279",
    service: "checkout-api",
    exception: "redis.exceptions.ConnectionError",
    message: "Connection closed by server",
    severity: "medium",
    count: 137,
    usersAffected: 0,
    firstSeen: minutesAgo(240),
    lastSeen: minutesAgo(31),
    stage: "unfixable",
    note: "The agent reproduced the call, but the failure is outside your code: the Redis instance closed the connection while the client held it idle. No patch to this repository will stop it. Raise the instance's timeout, or lower the client's idle window.",
    request: {
      method: "GET",
      path: "/v2/cart",
      status: 503,
      userAgent: "storefront-web/3.11.0",
      releaseSha: "9c41ab7",
    },
    frames: [
      {
        file: "app/cache/session.py",
        line: 44,
        fn: "get_cart",
        code: "raw = self._client.get(f\"cart:{cart_id}\")",
        blame: true,
      },
    ],
  },
];
