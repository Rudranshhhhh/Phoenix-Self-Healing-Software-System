"""Posts pipeline events to phoenix-api. Never raises: a dashboard outage must not stop healing."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional

log = logging.getLogger(__name__)


class IngestClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: float = 5.0) -> None:
        self.base_url = (base_url or os.environ.get("PHOENIX_API_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.token = token if token is not None else os.environ.get("PHOENIX_INGEST_TOKEN", "")
        self.timeout = timeout

    def send(self, incident_id: str, event: str, **fields: Any) -> Optional[dict]:
        payload = {"incident_id": incident_id, "event": event}
        payload.update({k: v for k, v in fields.items() if v is not None})
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Phoenix-Token"] = self.token
        request = urllib.request.Request(
            f"{self.base_url}/api/ingest/events",
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            log.warning("phoenix-api rejected %s (HTTP %s): %s", event, exc.code, body)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning("phoenix-api unreachable for %s: %s", event, exc)
        return None
