import hashlib
import hmac
import json

from app.config import config


def test_github_webhook_rejects_invalid_signature(client):
    response = client.post(
        "/api/github/webhook",
        headers={"X-GitHub-Event": "workflow_run", "X-Hub-Signature-256": "sha256=bad"},
        content=b"{}",
    )
    assert response.status_code == 401


def test_github_webhook_ignores_successful_run(client):
    body = json.dumps({"action": "completed", "workflow_run": {"conclusion": "success"}}).encode()
    signature = hmac.new(
        config.PHOENIX_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    response = client.post(
        "/api/github/webhook",
        headers={
            "X-GitHub-Event": "workflow_run",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        content=body,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
