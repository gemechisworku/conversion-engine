"""Lead-scoped reply-to address helpers."""

from __future__ import annotations

import base64
import re
from email.utils import parseaddr

_SAFE_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,62}[A-Za-z0-9]$")
_OPAQUE_PREFIX = "lid__"
_OPAQUE_SUFFIX = "__"


def build_lead_reply_local_part(lead_id: str) -> str:
    """Return a safe local-part for a lead-scoped reply address."""
    candidate = (lead_id or "").strip()
    if _is_safe_local_part(candidate):
        return candidate
    encoded = base64.urlsafe_b64encode(candidate.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_OPAQUE_PREFIX}{encoded}{_OPAQUE_SUFFIX}" if encoded else f"{_OPAQUE_PREFIX}unknown{_OPAQUE_SUFFIX}"


def build_lead_reply_address(*, lead_id: str, domain: str) -> str:
    local_part = build_lead_reply_local_part(lead_id)
    clean_domain = (domain or "").strip().lower()
    if not clean_domain:
        raise ValueError("reply domain is required")
    return f"{local_part}@{clean_domain}"


def extract_lead_id_from_reply_address(address: str, *, domain: str) -> str | None:
    _, parsed = parseaddr(address or "")
    candidate = (parsed or address or "").strip()
    if "@" not in candidate:
        return None
    local_part, host = candidate.rsplit("@", 1)
    if host.lower() != (domain or "").strip().lower():
        return None
    return decode_lead_id_from_local_part(local_part)


def decode_lead_id_from_local_part(local_part: str) -> str | None:
    token = (local_part or "").strip()
    if not token:
        return None
    if token.startswith(_OPAQUE_PREFIX) and token.endswith(_OPAQUE_SUFFIX):
        b64 = token[len(_OPAQUE_PREFIX) : -len(_OPAQUE_SUFFIX)]
        if not b64:
            return None
        try:
            padding = "=" * ((4 - len(b64) % 4) % 4)
            return base64.urlsafe_b64decode((b64 + padding).encode("ascii")).decode("utf-8")
        except Exception:
            return token if _is_safe_local_part(token) else None
    return token if _is_safe_local_part(token) else None


def _is_safe_local_part(value: str) -> bool:
    if not value or len(value) > 64:
        return False
    if value.startswith(".") or value.endswith(".") or ".." in value:
        return False
    return _SAFE_LOCAL_PART_RE.match(value) is not None
