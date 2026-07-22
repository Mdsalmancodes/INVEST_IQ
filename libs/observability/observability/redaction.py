"""Recursive redaction of secret-shaped fields before logging.

Per docs/architecture/05-data-pipeline-notifications-caching-monitoring.md §14.1:
logging middleware has an explicit deny-list of field names that are
automatically redacted before any log line is emitted, applied recursively to
nested objects. This is genuinely domain-specific policy (the deny-list is
ours), so it stays as custom code — but it is wired in as a *structlog
processor* (see logger.py) rather than a hand-rolled formatter, per the
"prefer a mature library over reinventing infrastructure" directive: the
serialization/formatting/context-propagation machinery itself is structlog's
job, not ours.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

REDACTED_VALUE = "[REDACTED]"

# Deny-list of field names (case-insensitive match). Extend here, never at
# individual call sites, so redaction stays centralized and can't be forgotten.
_SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "jwt_secret",
        "secret",
        "api_key",
        "apikey",
        "ssn",
        "card_number",
        "cardnumber",
        "cvv",
        "totp_secret",
        "totp_secret_encrypted",
    }
)


def redact(data: Any) -> Any:
    """Return a deep copy of ``data`` with sensitive fields replaced.

    Recurses into dicts and lists/tuples. Non-container values are returned
    unchanged. Dict keys are matched case-insensitively against the deny-list.
    """
    if isinstance(data, dict):
        return {
            key: REDACTED_VALUE
            if isinstance(key, str) and key.lower() in _SENSITIVE_FIELD_NAMES
            else redact(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact(item) for item in data)
    return data


def redaction_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor entry point — redacts the full event dict.

    Registered in the processor chain in logger.py. Runs before the JSON
    renderer so redaction always happens regardless of output format.

    Signature intentionally matches structlog.types.Processor exactly
    (logger: Any, method_name: str, event_dict: MutableMapping[str, Any]) ->
    Mapping[str, Any], so it slots into structlog's processor list without a
    type mismatch against structlog's own Processor type alias.
    """
    redacted = redact(dict(event_dict))
    assert isinstance(redacted, dict)  # redact() preserves dict shape for a dict input
    return redacted
