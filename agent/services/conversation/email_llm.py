"""LLM-backed first-touch and reply email drafting using Tenacious sales playbook (FR-7, FR-9)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.config.settings import Settings
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.enrichment.sales_playbook import (
    load_acknowledgement_policy,
    load_bench_summary_snippet,
    load_cold_email_playbook,
    load_style_guide,
)
from agent.services.observability.events import log_processing_step


class FirstTouchEmailDraftLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=120)
    text_body: str = Field(description="Plain text email body, max ~120 words")
    salutation_name_guess: str | None = Field(
        default=None,
        description="First name only if grounded in input; else null",
    )
    segment_pitch_angle: str = Field(description="One line: which ICP segment angle was used")
    grounded_claims: list[str] = Field(default_factory=list, description="Verifiable claims tied to briefs")


class InboundEmailInterpretLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["schedule", "interest", "clarification", "objection", "decline", "unclear"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary_one_line: str
    suggested_reply_subject: str = Field(max_length=120)
    suggested_reply_body: str
    next_best_action: Literal["schedule", "qualify", "clarify", "handle_objection", "nurture", "escalate"]
    meeting_time_from_thread: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "If the prospect stated a concrete meeting time, day, window, or timezone anywhere in "
            "CONVERSATION_THREAD or the latest inbound, copy it verbatim here; otherwise null."
        ),
    )


async def draft_first_touch_email_with_llm(
    *,
    settings: Settings,
    llm: OpenRouterJSONClient,
    company_name: str,
    prospect_first_name: str | None,
    icp_primary_segment: str,
    hiring_signal_brief: dict[str, Any],
    competitor_gap_brief: dict[str, Any],
    trace_id: str | None,
    lead_id: str | None,
) -> FirstTouchEmailDraftLLM | None:
    """OpenRouter: cold email #1 style — grounded, style_guide + cold sequence as constraints."""
    style = load_style_guide(settings)
    cold = load_cold_email_playbook(settings)
    ack = load_acknowledgement_policy(settings)
    bench = load_bench_summary_snippet(settings)
    if not style.strip() or not cold.strip():
        log_processing_step(
            component="conversation.email",
            step="email.draft.skip",
            message="First-touch LLM draft skipped: missing style_guide or cold sequence files",
            trace_id=trace_id,
            lead_id=lead_id,
        )
        return None

    user_payload = {
        "company_name": company_name,
        "prospect_first_name_hint": prospect_first_name,
        "icp_primary_segment": icp_primary_segment,
        "hiring_signal_brief": hiring_signal_brief,
        "competitor_gap_brief": competitor_gap_brief,
        "STYLE_GUIDE": style[:12_000],
        "COLD_EMAIL_PLAYBOOK": cold,
        "ACKNOWLEDGEMENT_AND_COMMS_POLICY": ack[:6_000] if ack else "",
        "BENCH_SUMMARY_SNIPPET": bench,
        "OUTPUT_SCHEMA": {
            "subject": "str, under 60 chars preferred, follow style guide (Request/Context/Question/Congrats patterns)",
            "text_body": "str, max 120 words, salutation with first name only if provided else 'there' avoided — use neutral professional opening per playbook",
            "salutation_name_guess": "str or null",
            "segment_pitch_angle": "str",
            "grounded_claims": ["list of short strings tied only to briefs"],
        },
    }
    return await llm.generate_model(
        system_prompt=(
            "You write the first cold outreach email for Tenacious Consulting. "
            "Obey STYLE_GUIDE tone markers (Direct, Grounded, Honest, Professional, Non-condescending). "
            "Follow COLD_EMAIL_PLAYBOOK structure for Email 1 (signal-grounded opener). "
            "Do not fabricate funding, roles, layoffs, or peer companies: only use hiring_signal_brief and competitor_gap_brief. "
            "If icp_primary_segment is 'abstain', use a generic exploratory opener without segment-specific pitch. "
            "Do not promise bench capacity beyond BENCH_SUMMARY_SNIPPET; prefer questions over assertions when confidence is weak. "
            "Include one clear ask (15 minutes). If you do not have a real Cal.com URL, phrase the ask as replying with availability — do not invent links."
        ),
        user_payload=user_payload,
        response_model=FirstTouchEmailDraftLLM,
        trace_id=trace_id,
        lead_id=lead_id,
        purpose="email.first_touch_draft",
    )


async def interpret_inbound_email_and_draft_reply(
    *,
    settings: Settings,
    llm: OpenRouterJSONClient,
    company_name: str,
    inbound_subject: str,
    inbound_body: str,
    recent_outbound_context: str | None,
    conversation_transcript: str | None,
    hiring_signal_brief: dict[str, Any] | None,
    trace_id: str | None,
    lead_id: str | None,
) -> InboundEmailInterpretLLM | None:
    """OpenRouter: classify real inbound email and draft a professional reply (warm tone allowed after prospect wrote)."""
    style = load_style_guide(settings)
    if not style.strip():
        return None

    transcript = (conversation_transcript or "").strip()
    if len(transcript) > 24_000:
        transcript = "…(earlier thread omitted)\n\n" + transcript[-24_000:]

    user_payload = {
        "company_name": company_name,
        "inbound_email_subject": inbound_subject,
        "inbound_email_body": inbound_body,
        "recent_outbound_context": recent_outbound_context or "",
        "CONVERSATION_THREAD": transcript,
        "hiring_signal_brief_excerpt": json.dumps(hiring_signal_brief or {}, default=str)[:8_000],
        "STYLE_GUIDE": style[:10_000],
        "INTENT_LABELS": [
            "schedule",
            "interest",
            "clarification",
            "objection",
            "decline",
            "unclear",
        ],
        "NEXT_ACTION_LABELS": [
            "schedule",
            "qualify",
            "clarify",
            "handle_objection",
            "nurture",
            "escalate",
        ],
    }
    return await llm.generate_model(
        system_prompt=(
            "You analyze a real inbound sales email reply and draft Tenacious's next email. "
            "You may receive CONVERSATION_THREAD: chronological prior + current email thread (may be empty). "
            "Use the entire thread for intent and scheduling: if the prospect stated a meeting day, time, window, "
            "or timezone in an earlier message or the latest inbound, you MUST reflect it in meeting_time_from_thread "
            "and in suggested_reply_body when next_best_action is schedule (confirm that exact preference; do not invent a different slot). "
            "Classify intent conservatively from the latest inbound in light of the thread. "
            "Map intent to next_best_action: "
            "schedule->schedule, interest->qualify, clarification->clarify, objection->handle_objection, "
            "decline->nurture, unclear->clarify. "
            "Follow STYLE_GUIDE; warm replies may mirror the prospect's tone slightly but stay professional. "
            "Do not fabricate product facts; offer clear next steps. "
            "suggested_reply_body should be ready to send as plain text."
        ),
        user_payload=user_payload,
        response_model=InboundEmailInterpretLLM,
        trace_id=trace_id,
        lead_id=lead_id,
        purpose="email.inbound_interpret_and_reply",
    )
