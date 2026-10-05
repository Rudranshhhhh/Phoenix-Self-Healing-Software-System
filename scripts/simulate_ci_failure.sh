#!/bin/bash
# Simulate a GitHub Actions CI failure → Phoenix incident
# Usage: ./scripts/simulate_ci_failure.sh

set -e

PHOENIX_URL="${PHOENIX_URL:-http://localhost:8000}"
PHOENIX_WEBHOOK_SECRET="${PHOENIX_WEBHOOK_SECRET:-local-dev-secret}"
REPO="${CI_REPO:-owner/repo}"
COMMIT="${CI_COMMIT:-abc1234567890def1234567890def12345678901}"
BRANCH="${CI_BRANCH:-main}"
RUN_ID="${CI_RUN_ID:-1234567890}"

# Minimal CI logs showing a Python exception
LOGS="
test_app.py::test_get_username FAILED

test_app.py:10: in test_get_username
    assert get_username(user) == 'Alice'
app.py:3: in get_username
    return user['name']
E   KeyError: 'name'

================================ 1 failed in 0.42s ================================
"

echo "🚀 Simulating GitHub Actions CI failure"
echo "Phoenix URL: $PHOENIX_URL"
echo "Repository: $REPO"
echo "Commit: $COMMIT"
echo ""
echo "Sending webhook payload..."

curl -v -X POST "$PHOENIX_URL/api/incidents" \
  -H "Content-Type: application/json" \
  -H "X-Phoenix-Token: $PHOENIX_WEBHOOK_SECRET" \
  -d @- << EOF
{
  "source": "github_ci",
  "repository": "$REPO",
  "commit": "$COMMIT",
  "branch": "$BRANCH",
  "run_id": "$RUN_ID",
  "run_url": "https://github.com/$REPO/actions/runs/$RUN_ID",
  "workflow": "tests",
  "job": "test",
  "stage": "test",
  "logs": "$LOGS"
}
EOF

echo ""
echo "✓ Webhook sent. Phoenix is processing the incident in the background."
echo ""
echo "Check the incident status:"
echo "  curl http://localhost:8000/api/incidents"
echo ""
