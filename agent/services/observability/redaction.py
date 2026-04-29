"""Sensitive-data redaction helpers for trace payloads."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEYS_EXACT = {
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "secret",
    "password",
    "phone",
    "phone_number",
    "from_number",
    "to_number",
    "access_token",
    "refresh_token",
    "bearer_token",
}
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9\-\._~\+/]+=*")


def redact_value(value: Any) -> Any:
    """Redact obvious secret values recursively."""
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if _is_sensitive_key(key) else redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, str):
        masked = _BEARER_RE.sub("Bearer <redacted>", value)
        return masked
    return value


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in _SENSITIVE_KEYS_EXACT:
        return True
    if lowered.endswith("_api_key"):
        return True
    if lowered.endswith("_token") and lowered not in {"tokens_input", "tokens_output"}:
        return True
    return False
