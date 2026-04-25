"""Outreach draft → review → send (specs/api_contracts/outreach_api.md + outreach_generation_and_review.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.config.settings import Settings
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.email.client import EmailService
from agent.services.email.reply_address import build_lead_reply_address
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.observability.langfuse_llm import langfuse_workflow_span
from agent.services.observability.events import log_processing_step
from agent.services.outreach.outreach_payload import parse_outreach_stored, wrap_v2
from agent.services.outreach.tone_claim_reviewer import (
    map_review_to_outbound_review_status,
    run_tone_claim_review,
)
from agent.services.orchestration.outreach_pipeline import build_first_touch_outreach_request_async
from agent.services.policy.outbound_policy import OutboundPolicyService


@dataclass
class OutreachFlowDeps:
    settings: Settings
    state_repo: SQLiteStateRepository
    llm: OpenRouterJSONClient | None
    policy: OutboundPolicyService


async def run_outreach_draft_only(
    deps: OutreachFlowDeps,
    *,
    lead_id: str,
    trace_id: str,
    idempotency_key: str,
    to_email: str,
    company_name: str,
    variant: str,
    brief_id: str | None,
    gap_brief_id: str | None,
    prospect_first_name: str | None = None,
) -> OutboundEmailRequest:
    """POST /outreach/draft — persist outbound only; review runs separately (spec)."""
    with langfuse_workflow_span(
        deps.settings,
        trace_id=trace_id,
        lead_id=lead_id,
        name="outreach.draft",
    ):
        briefs = deps.state_repo.get_briefs(lead_id=lead_id) or {}
        if brief_id and isinstance(briefs.get("hiring_signal_brief"), dict):
            _ = brief_id
        if gap_brief_id and isinstance(briefs.get("competitor_gap_brief"), dict):
            _ = gap_brief_id
        req = await build_first_touch_outreach_request_async(
            settings=deps.settings,
            llm=deps.llm,
            lead_id=lead_id,
            to_email=to_email,
            company_name=company_name,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            briefs=briefs,
            prospect_first_name=prospect_first_name,
        )
        dumped = req.model_dump(mode="json")
        dumped["review_status"] = "pending"
        outbound = OutboundEmailRequest.model_validate(dumped)
        env = wrap_v2(outbound=outbound.model_dump(mode="json"), review=None)
        deps.state_repo.upsert_outreach_draft(lead_id=lead_id, draft=env)
        meta = outbound.metadata or {}
        claims = meta.get("grounded_claims") or []
        tid = (trace_id or "").strip() or f"outreach:{lead_id}"
        if isinstance(claims, list):
            for idx, raw in enumerate(claims):
                text = raw.strip() if isinstance(raw, str) else ""
                if not text:
                    continue
                deps.state_repo.append_evidence_edge(
                    lead_id=lead_id,
                    trace_id=tid,
                    edge_type="outreach.grounded_claim",
                    claim_ref=f"grounded_claim_{idx}",
                    brief_id=None,
                    source_ref=outbound.draft_id,
                    payload={"claim": text[:2000]},
                )
        log_processing_step(
            component="outreach.flow",
            step="draft.persisted",
            message="Outreach draft stored (awaiting review per outreach_api)",
            lead_id=lead_id,
            trace_id=trace_id,
            draft_id=outbound.draft_id,
            variant=variant,
        )
        return outbound


async def run_outreach_review_for_lead(
    deps: OutreachFlowDeps,
    *,
    lead_id: str,
    draft_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """POST /outreach/review — tone/claim reviewer over stored draft."""
    with langfuse_workflow_span(
        deps.settings,
        trace_id=trace_id,
        lead_id=lead_id,
        name="outreach.review",
    ):
        row = deps.state_repo.get_outreach_draft(lead_id=lead_id)
        if row is None:
            raise ValueError("No draft for lead_id.")
        raw = row["draft"]
        outbound_d, _existing_rev = parse_outreach_stored(raw)
        outbound = OutboundEmailRequest.model_validate(outbound_d)
        if outbound.draft_id != draft_id:
            raise ValueError("draft_id does not match stored draft.")
        briefs = deps.state_repo.get_briefs(lead_id=lead_id) or {}
        hiring = briefs.get("hiring_signal_brief") if isinstance(briefs.get("hiring_signal_brief"), dict) else {}
        gap = briefs.get("competitor_gap_brief") if isinstance(briefs.get("competitor_gap_brief"), dict) else {}
        rec = await run_tone_claim_review(
            settings=deps.settings,
            policy=deps.policy,
            llm=deps.llm,
            outbound=outbound,
            hiring_signal_brief=hiring,
            competitor_gap_brief=gap,
            trace_id=trace_id,
            lead_id=lead_id,
        )
        rs = map_review_to_outbound_review_status(rec)
        dumped = outbound.model_dump(mode="json")
        dumped["review_status"] = rs
        if rec.review_id:
            dumped["review_id"] = rec.review_id
        outbound2 = OutboundEmailRequest.model_validate(dumped)
        review_blob = rec.model_dump(mode="json")
        deps.state_repo.upsert_outreach_draft(
            lead_id=lead_id,
            draft=wrap_v2(outbound=outbound2.model_dump(mode="json"), review=review_blob),
        )
        return review_blob


async def run_outreach_send_for_lead(
    deps: OutreachFlowDeps,
    *,
    lead_id: str,
    draft_id: str,
    review_id: str,
    trace_id: str,
    idempotency_key: str,
    to_email: str | None,
    email_service: EmailService | None,
    override_text_body: str | None = None,
) -> tuple[str | None, str | None]:
    """POST /outreach/send — guardrails per outreach_api.md §Guardrails."""
    with langfuse_workflow_span(
        deps.settings,
        trace_id=trace_id,
        lead_id=lead_id,
        name="outreach.send",
    ):
        row = deps.state_repo.get_outreach_draft(lead_id=lead_id)
        if row is None:
            return None, "No draft for lead_id."
        outbound_d, review = parse_outreach_stored(row["draft"])
        outbound = OutboundEmailRequest.model_validate(outbound_d)
        if outbound.draft_id != draft_id:
            return None, "draft_id mismatch."
        if not review:
            return None, "No approved review exists."
        if review.get("review_id") != review_id:
            return None, "review_id mismatch."
        if not review.get("final_send_ok"):
            return None, "Review does not allow send (final_send_ok is false)."
        if review.get("status") not in ("approved", "approved_with_edits"):
            return None, f"Review status '{review.get('status')}' is not send-eligible."
        rs = outbound.review_status
        if rs not in ("approved", "approved_with_edits"):
            return None, f"Outbound review_status '{rs}' blocks send."
        if email_service is None:
            log_processing_step(
                component="outreach.flow",
                step="send.skipped",
                message="EmailService not configured; send not executed",
                lead_id=lead_id,
                trace_id=trace_id,
            )
            return "skipped_no_email_service", None
        dest = (to_email or "").strip() or deps.settings.default_outreach_to_email.strip()
        if not dest or "@" not in dest or dest.endswith("invalid.local"):
            return None, "Valid to_email required for send."
        merged = {
            **outbound.model_dump(mode="json"),
            "to_email": dest,
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
        }
        if override_text_body is not None:
            merged["text_body"] = override_text_body
        req = OutboundEmailRequest.model_validate(merged)
        res = await email_service.send_email(req)
        if not res.accepted:
            return None, res.error.error_message if res.error else "send_failed"
        deps.state_repo.mark_outreach_sent_idempotency(lead_id=lead_id, idempotency_key=idempotency_key)
        mid = res.provider_message_id or f"queued_{idempotency_key[:12]}"
        meta = req.metadata or {}
        reply_to_address = str(meta.get("reply_to_address") or "").strip() or build_lead_reply_address(
            lead_id=lead_id,
            domain=deps.settings.resend_reply_domain,
        )
        deps.state_repo.append_message(
            lead_id=lead_id,
            channel="email",
            message_id=f"outreach_sent_{idempotency_key[:16]}",
            direction="outbound",
            content=req.text_body or "",
            metadata={
                "subject": req.subject,
                "kind": "first_touch_sent",
                "resend_message_id": res.provider_message_id,
                "draft_id": req.draft_id,
                "review_id": review_id,
                "email_thread_id": meta.get("email_thread_id"),
                "reply_to_address": reply_to_address,
                "resend_raw_response": res.raw_response or {},
            },
        )
        return mid, None
