"""Error hierarchy for metarelay with sensitive data redaction."""

from __future__ import annotations

import re


class MetarelayError(Exception):
    """Base exception for all metarelay errors."""

    pass


class ConfigError(MetarelayError):
    """Configuration loading or validation error."""

    pass


class ConnectionError(MetarelayError):
    """Failed to connect to Supabase or other remote service."""

    pass


class DispatchError(MetarelayError):
    """Handler dispatch or execution failure."""

    pass


class EventStoreError(MetarelayError):
    """Local event store (SQLite) error."""

    pass


# Patterns for sensitive data redaction
_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # GitHub tokens
    (re.compile(r"ghp_[A-Za-z0-9_]{36,}"), "<REDACTED_TOKEN>"),
    (re.compile(r"gho_[A-Za-z0-9_]{36,}"), "<REDACTED_TOKEN>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "<REDACTED_TOKEN>"),
    # Supabase keys (JWT-like)
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{20,}" r"\.[A-Za-z0-9_-]{20,}" r"\.[A-Za-z0-9_-]{20,}"),
        "<REDACTED_JWT>",
    ),
    # URL credentials
    (re.compile(r"://[^@\s]+:[^@\s]+@"), "://<REDACTED_CREDS>@"),
    # Authorization headers
    (re.compile(r"(Authorization:\s*Bearer\s+)\S+", re.IGNORECASE), r"\1<REDACTED_TOKEN>"),
    # Generic secret-like values (webhook secrets, etc.)
    (
        re.compile(
            r"(secret[\"']?\s*[:=]\s*[\"']?)" r"[A-Za-z0-9_-]{16,}",
            re.IGNORECASE,
        ),
        r"\1<REDACTED_SECRET>",
    ),
]


def redact_error(error: Exception) -> MetarelayError:
    """Wrap an exception, redacting sensitive data from its message.

    Args:
        error: The original exception.

    Returns:
        A MetarelayError with redacted message and original preserved.
    """
    message = str(error)
    for pattern, replacement in _REDACTION_PATTERNS:
        message = pattern.sub(replacement, message)

    redacted = MetarelayError(message)
    redacted.__cause__ = error
    return redacted
