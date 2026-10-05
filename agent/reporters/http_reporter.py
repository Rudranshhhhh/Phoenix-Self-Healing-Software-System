"""
Phoenix Agent — HTTP Reporter

POSTs incidents and metrics to either:
  - Phoenix API (port 8000, /api/incidents with X-Phoenix-Token header)
  - Flask backend (port 5000, /api/incidents, legacy)

Uses requests with retry on transient failures.
Never raises — all exceptions are caught and logged.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests
import requests.adapters
from urllib3.util.retry import Retry

from agent.events.incident import Incident, ServiceSnapshot

logger = logging.getLogger(__name__)


def _build_session(max_retries: int = 3) -> requests.Session:
    """Build a requests session with exponential backoff retry."""
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=1.0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST", "PATCH"],
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _detect_phoenix_api_url(backend_url: str) -> Optional[str]:
    """
    Auto-detect if backend_url points to Flask backend (port 5000).
    If so, return the Phoenix API URL (port 8000).
    Otherwise, return None (backend_url is already Phoenix API or explicit).
    """
    if ":5000" in backend_url or backend_url.endswith("5000"):
        # Legacy Flask backend — convert to Phoenix API
        phoenix_url = backend_url.replace(":5000", ":8000").replace("/5000", "/8000")
        logger.info(
            "HTTPReporter: detected Flask backend at %s, using Phoenix API at %s",
            backend_url, phoenix_url
        )
        return phoenix_url
    
    # Check PHOENIX_API_URL env var (explicit override)
    phoenix_url = os.environ.get("PHOENIX_API_URL")
    if phoenix_url:
        logger.info("HTTPReporter: using PHOENIX_API_URL from environment: %s", phoenix_url)
        return phoenix_url
    
    return None


class HTTPReporter:
    """
    Reports incidents and metrics to either Phoenix API or Flask backend.
    
    Phoenix API (preferred):
      - URL: http://phoenix-api:8000 or http://localhost:8000
      - Auth: X-Phoenix-Token header (PHOENIX_WEBHOOK_SECRET env var)
      - Payload: source=docker_runtime
      - Dedup: (container_name, error_type) tuple for Docker incidents
    
    Flask backend (legacy):
      - URL: http://phoenix-backend:5000 or http://localhost:5000
      - Auth: None
      - Payload: Full Incident object
    """

    def __init__(self, backend_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = backend_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session = _build_session()
        
        # Detect if we should use Phoenix API instead
        self._phoenix_api_url = _detect_phoenix_api_url(backend_url)
        self._webhook_secret = os.environ.get("PHOENIX_WEBHOOK_SECRET", "")
        
        if self._phoenix_api_url:
            logger.info(
                "HTTPReporter: targeting Phoenix API at %s (will send docker_runtime incidents)",
                self._phoenix_api_url
            )

    def _incident_to_docker_payload(self, incident: Incident) -> dict:
        """Convert agent Incident to DockerIncidentPayload for Phoenix API."""
        metrics = incident.metrics_snapshot
        logs = "\n".join(metrics.log_errors) if metrics.log_errors else ""
        
        # Build dedup key: container + error type (for Docker runtime incidents)
        return {
            "source": "docker_runtime",
            "repository": os.environ.get("GITHUB_REPOSITORY", "unknown/repo"),
            "commit": os.environ.get("GITHUB_SHA", "unknown"),
            "branch": os.environ.get("GITHUB_REF_NAME", "unknown"),
            "container_name": incident.container_name,
            "error_type": incident.failure_type.value,  # e.g., CONTAINER_DOWN
            "error_message": f"{incident.service} — {incident.root_cause or incident.failure_type.value}",
            "logs": logs,
            "stack_trace": None,
        }

    def report_incident(self, incident: Incident) -> None:
        """POST the incident to Phoenix API or Flask backend."""
        
        # Use Phoenix API if available
        if self._phoenix_api_url:
            self._report_to_phoenix_api(incident)
        else:
            self._report_to_flask_backend(incident)
    
    def _report_to_phoenix_api(self, incident: Incident) -> None:
        """POST Docker runtime incident to Phoenix API."""
        url = f"{self._phoenix_api_url}/api/incidents"
        payload = self._incident_to_docker_payload(incident)
        
        headers = {
            "Content-Type": "application/json",
        }
        if self._webhook_secret:
            headers["X-Phoenix-Token"] = self._webhook_secret
        
        try:
            response = self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.info(
                "HTTPReporter: Docker incident '%s' sent to Phoenix API (status=%d)",
                incident.incident_id, response.status_code,
            )
        except requests.exceptions.Timeout:
            logger.warning("HTTPReporter: timeout sending incident to Phoenix API: %s", incident.incident_id)
        except requests.exceptions.ConnectionError:
            logger.warning("HTTPReporter: cannot connect to Phoenix API at %s", self._phoenix_api_url)
        except Exception as exc:
            logger.exception("HTTPReporter: error sending incident to Phoenix API: %s", exc)
    
    def _report_to_flask_backend(self, incident: Incident) -> None:
        """POST incident to Flask backend (legacy)."""
        url = f"{self._base_url}/api/incidents"
        try:
            response = self._session.post(
                url,
                json=incident.to_dict(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.debug(
                "HTTPReporter: incident '%s' sent to Flask backend (status=%d)",
                incident.incident_id, response.status_code,
            )
        except requests.exceptions.Timeout:
            logger.warning("HTTPReporter: timeout sending incident '%s'", incident.incident_id)
        except requests.exceptions.ConnectionError:
            logger.warning("HTTPReporter: cannot connect to backend at %s", self._base_url)
        except Exception as exc:
            logger.exception("HTTPReporter: error sending incident: %s", exc)

    def report_metric(self, snapshot: ServiceSnapshot) -> None:
        """POST a metrics snapshot to /api/metrics."""
        url = f"{self._base_url}/api/metrics"
        try:
            response = self._session.post(
                url,
                json=snapshot.to_dict(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.debug(
                "HTTPReporter: metric for '%s' sent (status=%d)",
                snapshot.service, response.status_code,
            )
        except requests.exceptions.Timeout:
            logger.warning("HTTPReporter: timeout sending metric for '%s'", snapshot.service)
        except requests.exceptions.ConnectionError:
            logger.warning("HTTPReporter: cannot connect to backend at %s", self._base_url)
        except Exception as exc:
            logger.exception("HTTPReporter: error sending metric: %s", exc)
