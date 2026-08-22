"""
Phoenix Agent — HTTP Reporter

POSTs incidents and metrics to the Flask backend REST API.
Uses requests with retry on transient failures.
Never raises — all exceptions are caught and logged.
"""
from __future__ import annotations

import logging
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


class HTTPReporter:
    """
    Reports incidents and metrics to the Flask backend via REST.

    POST /api/incidents  — create or update incident
    POST /api/metrics    — ingest time-series metric point
    """

    def __init__(self, backend_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = backend_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session = _build_session()

    def report_incident(self, incident: Incident) -> None:
        """POST the full incident document to /api/incidents."""
        url = f"{self._base_url}/api/incidents"
        try:
            response = self._session.post(
                url,
                json=incident.to_dict(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.debug(
                "HTTPReporter: incident '%s' sent (status=%d)",
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
