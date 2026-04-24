"""Resend inbound webhook persistence for email threads."""

from __future__ import annotations

from typing import Any

from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.email.rfc_ids import merge_references_header, normalize_message_id
from agent.services.email.schemas import InboundEmailEvent


def extract_lead_id_from_resend_data(data: dict[str, Any]) -> str | None:
    """Resolve lead_id from inbound webhook data (custom headers or metadata)."""
    headers = data.get("headers")
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == "x-lead-id" and value:
                return str(value).strip()
    meta = data.get("metadata")
    if isinstance(meta, dict) and meta.get("lead_id"):
        return str(meta["lead_id"]).strip()
    direct = data.get("lead_id")
    if direct:
        return str(direct).strip()
    return None


async def persist_inbound_resend_webhook(*, state_repo: SQLiteStateRepository, event: InboundEmailEvent) -> None:
    """Update email_threads from a normalized inbound Resend event (no duplicate message_log by default)."""
    if event.event_type != "reply" or event.error is not None:
        return
    data = event.raw_payload.get("data") if isinstance(event.raw_payload.get("data"), dict) else {}
    lead_id = extract_lead_id_from_resend_data(data)
    if not lead_id:
        return
    inbound_rfc = normalize_message_id(event.rfc_message_id)
    if not inbound_rfc:
        return
    prior = merge_references_header(event.references, event.in_reply_to)
    state_repo.email_thread_record_inbound(
        lead_id=lead_id,
        inbound_rfc_message_id=inbound_rfc,
        prior_references_fragment=prior or None,
    )
