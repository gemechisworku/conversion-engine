"""Resend inbound webhook persistence for email threads."""

from __future__ import annotations

import logging
from typing import Any

from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.email.reply_address import extract_lead_id_from_reply_address
from agent.services.email.rfc_ids import merge_references_header, normalize_message_id
from agent.services.email.schemas import InboundEmailEvent

LOGGER = logging.getLogger("agent.services.email.threading")


def extract_lead_id_from_resend_data(
    data: dict[str, Any],
    *,
    event: InboundEmailEvent | None = None,
    reply_domain: str = "chuairkoon.resend.app",
) -> str | None:
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
    recipient_candidates: list[str] = []
    to_field = data.get("to")
    if isinstance(to_field, list):
        recipient_candidates.extend(str(v) for v in to_field if v)
    elif to_field:
        recipient_candidates.append(str(to_field))
    if data.get("to_email"):
        recipient_candidates.append(str(data["to_email"]))
    if isinstance(event, InboundEmailEvent) and event.to_email:
        recipient_candidates.append(event.to_email)
    for candidate in recipient_candidates:
        lead_id = extract_lead_id_from_reply_address(candidate, domain=reply_domain)
        if lead_id:
            return lead_id
    return None


async def persist_inbound_resend_webhook(
    *,
    state_repo: SQLiteStateRepository,
    event: InboundEmailEvent,
    reply_domain: str = "chuairkoon.resend.app",
) -> str | None:
    """Update email_threads from a normalized inbound Resend event (no duplicate message_log by default)."""
    if event.event_type != "reply" or event.error is not None:
        return None
    data = event.raw_payload.get("data") if isinstance(event.raw_payload.get("data"), dict) else {}
    lead_id = extract_lead_id_from_resend_data(data, event=event, reply_domain=reply_domain)
    if not lead_id:
        LOGGER.warning(
            "Unable to resolve lead_id from inbound email webhook",
            extra={"payload_ref": event.raw_payload_ref, "to_email": event.to_email},
        )
        return None
    inbound_rfc = normalize_message_id(event.rfc_message_id)
    if not inbound_rfc:
        return lead_id
    prior = merge_references_header(event.references, event.in_reply_to)
    state_repo.email_thread_record_inbound(
        lead_id=lead_id,
        inbound_rfc_message_id=inbound_rfc,
        prior_references_fragment=prior or None,
    )
    return lead_id
