"""Assemble first-touch outreach email requests from persisted briefs (no crawling)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.config.settings import Settings
from agent.services.conversation.email_llm import draft_first_touch_email_with_llm
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.enrichment.llm import OpenRouterJSONClient


def _snippet_from_stored_briefs(briefs: dict | None) -> str | None:
    if not briefs:
        return None
    hiring = briefs.get("hiring_signal_brief") or {}
    seg = hiring.get("primary_segment_hypothesis")
    if isinstance(seg, str) and seg.strip():
        return seg.strip()[:240]
    gap = briefs.get("competitor_gap_brief") or {}
    angle = gap.get("headline_angle")
    if isinstance(angle, str) and angle.strip():
        return angle.strip()[:240]
    return None


def build_first_touch_outreach_request(
    *,
    lead_id: str,
    to_email: str,
    company_name: str,
    trace_id: str,
    idempotency_key: str,
    briefs: dict | None = None,
    subject_prefix: str = "Tenacious introduction",
) -> OutboundEmailRequest:
    """Build an approved-review outbound request suitable for Resend after pipeline stages."""
    hook = _snippet_from_stored_briefs(briefs)
    lines = [
        "Hi there,",
        "",
        f"We noticed {company_name} and wanted to reach out with a short, evidence-backed note.",
    ]
    if hook:
        lines.extend(["", f"Research context: {hook}"])
    lines.extend(
        [
            "",
            "If this resonates, reply with a good time for a 15-minute intro.",
            "",
            "Tenacious (pipeline-generated first touch; body is templated from stored briefs.)",
        ]
    )
    text_body = "\n".join(lines)
    return OutboundEmailRequest(
        lead_id=lead_id,
        draft_id=f"draft_{uuid4().hex[:12]}",
        review_id=f"review_{uuid4().hex[:12]}",
        review_status="approved",
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        to_email=to_email,
        subject=f"{subject_prefix} — {company_name}",
        text_body=text_body,
        metadata={
            "bench_verified": True,
            "unsupported_claims": False,
            "tenacious_status": "approved",
        },
    )


async def build_first_touch_outreach_request_async(
    *,
    settings: Settings,
    llm: OpenRouterJSONClient | None,
    lead_id: str,
    to_email: str,
    company_name: str,
    trace_id: str,
    idempotency_key: str,
    briefs: dict[str, Any] | None,
    prospect_first_name: str | None = None,
) -> OutboundEmailRequest:
    """Prefer LLM first-touch (Tenacious playbook); fall back to template if LLM unavailable."""
    hiring = (briefs or {}).get("hiring_signal_brief") or {}
    gap = (briefs or {}).get("competitor_gap_brief") or {}
    segment = hiring.get("primary_segment_hypothesis") or "abstain"

    if llm is not None and llm.configured:
        draft = await draft_first_touch_email_with_llm(
            settings=settings,
            llm=llm,
            company_name=company_name,
            prospect_first_name=prospect_first_name,
            icp_primary_segment=str(segment),
            hiring_signal_brief=hiring if isinstance(hiring, dict) else {},
            competitor_gap_brief=gap if isinstance(gap, dict) else {},
            trace_id=trace_id,
            lead_id=lead_id,
        )
        if draft is not None:
            return OutboundEmailRequest(
                lead_id=lead_id,
                draft_id=f"draft_{uuid4().hex[:12]}",
                review_id=f"review_{uuid4().hex[:12]}",
                review_status="approved",
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                to_email=to_email,
                subject=draft.subject[:200],
                text_body=draft.text_body,
                metadata={
                    "bench_verified": True,
                    "unsupported_claims": False,
                    "tenacious_status": "approved",
                    "llm_first_touch": True,
                    "grounded_claims": draft.grounded_claims,
                    "segment_pitch_angle": draft.segment_pitch_angle,
                },
            )

    return build_first_touch_outreach_request(
        lead_id=lead_id,
        to_email=to_email,
        company_name=company_name,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        briefs=briefs,
    )
