"""
Phoenix API — Failure Classifier

Classify whether a failure is code-level (patchable) or infra-level (not patchable).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FailureClassifier:
    """Classify failures as code-level or non-code."""

    # Patterns that indicate non-code failures
    NON_CODE_PATTERNS = {
        # Network/infra
        "connection timeout",
        "connection refused",
        "network error",
        "host not reachable",
        "dns resolution failed",
        "certificate error",
        "ssl error",
        "tls error",
        # Authentication / secrets
        "authentication failed",
        "unauthorized",
        "forbidden",
        "invalid credentials",
        "api key",
        "token expired",
        # Infrastructure
        "disk full",
        "out of memory",
        "permission denied",
        "resource exhausted",
        "cpu throttled",
        # External services / rate limiting
        "rate limit",
        "throttled",
        "service unavailable",
        "gateway timeout",
        "503",
        "502",
        # Dependency / registry issues
        "package not found",
        "no matching distribution",
        "dependency resolution",
        "registry unreachable",
        "pip index",
        # Runner / CI infra
        "runner out of space",
        "runner disconnected",
        "ci timeout",
    }

    CODE_ERROR_TYPES = {
        "TypeError",
        "ValueError",
        "KeyError",
        "AttributeError",
        "IndexError",
        "AssertionError",
        "ImportError",
        "RuntimeError",
        "NameError",
        "UnboundLocalError",
        "ZeroDivisionError",
    }

    @classmethod
    def classify(
        cls,
        error_type: str,
        error_message: str,
        logs: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Classify a failure.
        Returns (classification, reason) where classification is
        "code" (patchable) or "non_code" (not patchable).
        """
        # Check error type against known code exceptions
        if error_type in cls.CODE_ERROR_TYPES:
            return "code", f"Code-level error: {error_type}"

        # Check combined error message
        combined = f"{error_type} {error_message}".lower()
        combined += f" {logs.lower() if logs else ''}"

        for pattern in cls.NON_CODE_PATTERNS:
            if pattern in combined:
                return (
                    "non_code",
                    f"Infrastructure/environment issue: {pattern}",
                )

        # Default: assume code-level (conservative — attempt to patch)
        return "code", "Unknown error type, assuming code-level"
