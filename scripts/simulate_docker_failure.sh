#!/bin/bash
# Simulate a Docker runtime failure → Phoenix incident
# Usage: ./scripts/simulate_docker_failure.sh

set -e

PHOENIX_URL="${PHOENIX_URL:-http://localhost:8000}"
PHOENIX_WEBHOOK_SECRET="${PHOENIX_WEBHOOK_SECRET:-local-dev-secret}"
REPO="${DOCKER_REPO:-owner/repo}"
COMMIT="${DOCKER_COMMIT:-abc1234567890def1234567890def12345678901}"
BRANCH="${DOCKER_BRANCH:-main}"

echo "🚀 Simulating Docker runtime failure"
echo "Phoenix URL: $PHOENIX_URL"
echo "Repository: $REPO"
echo "Commit: $COMMIT"
echo ""
echo "Sending incident payload..."

curl -v -X POST "$PHOENIX_URL/api/incidents" \
  -H "Content-Type: application/json" \
  -H "X-Phoenix-Token: $PHOENIX_WEBHOOK_SECRET" \
  -d @- << EOF
{
  "source": "docker_runtime",
  "repository": "$REPO",
  "commit": "$COMMIT",
  "branch": "$BRANCH",
  "container_name": "user-service-1",
  "error_type": "TypeError",
  "error_message": "'NoneType' object is not subscriptable",
  "logs": "Traceback (most recent call last):\\n  File \\\"app.py\\\", line 42, in get_user\\n    return user['name']\\nTypeError: 'NoneType' object is not subscriptable\\n",
  "stack_trace": "Traceback (most recent call last):\\n  File 'app.py', line 42, in get_user\\n    return user['name']\\nTypeError: 'NoneType' object is not subscriptable"
}
EOF

echo ""
echo "✓ Incident sent. Phoenix is processing it in the background."
echo ""
echo "Check the incident status:"
echo "  curl http://localhost:8000/api/incidents"
echo ""
