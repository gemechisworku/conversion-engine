"""Normalize persisted outreach payloads (v1 flat OutboundEmailRequest vs v2 envelope)."""

from __future__ import annotations

from typing import Any


def is_v2_envelope(data: dict[str, Any]) -> bool:
    return "outbound" in data and isinstance(data.get("outbound"), dict)


def parse_outreach_stored(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return (outbound_email_request_dict, review_record_or_none)."""
    if is_v2_envelope(data):
        out = data["outbound"]
        rev = data.get("review")
        return out, rev if isinstance(rev, dict) else None
    return data, None


def wrap_v2(*, outbound: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any]:
    return {"version": 2, "outbound": outbound, "review": review}
