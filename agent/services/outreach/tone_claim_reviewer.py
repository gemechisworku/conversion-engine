"""Tone-and-claim reviewer (specs/agents/tone_and_claim_reviewer_spec.md) — policy + heuristics + optional LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent.config.settings import Settings
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.observability.events import log_processing_step, log_trace_event
from agent.services.outreach.reviewer_tools import (
    ReviewerToolResult,
    aggregate_tool_failures,
    run_reviewer_tool_sequence,
)
from agent.services.policy.outbound_policy import OutboundPolicyService


def _load_reviewer_system_prompt() -> str:
    path = Path(__file__).resolve().parents[2] / "prompts" / "reviewer_system.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        "You are Tenacious tone-and-claim reviewer. Return JSON only. "
        "Reject unsupported factual claims vs briefs; flag hype; require softer language when confidence is weak. "
        "final_send_ok true only for approved or approved_with_edits with no blocking issues."
    )


class ToneClaimReviewRecord(BaseModel):
    """Aligned to tone_and_claim_reviewer_spec.md §5."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    draft_id: str
    status: Literal["approved", "approved_with_edits", "pending", "rejected"]
    issues: list[str] = Field(default_factory=list)
    required_rewrites: list[str] = Field(default_factory=list)
    final_send_ok: bool


class ReviewerLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "approved_with_edits", "pending", "rejected"]
    issues: list[str] = Field(default_factory=list)
    required_rewrites: list[str] = Field(default_factory=list)
    final_send_ok: bool


def _heuristic_screen(req: OutboundEmailRequest) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    rewrites: list[str] = []
    meta = req.metadata or {}
    if meta.get("unsupported_claims"):
        issues.append("unsupported_claim_flagged")
    body = (req.text_body or "").lower()
    for m in ("guaranteed", "100% success", "promise you ", "risk-free"):
        if m in body:
            issues.append("hype_language")
            rewrites.append("Soften or remove absolute claims; prefer questions over assertions.")
    return issues, rewrites


async def run_tone_claim_review(
    *,
    settings: Settings,
    policy: OutboundPolicyService,
    llm: OpenRouterJSONClient | None,
    outbound: OutboundEmailRequest,
    hiring_signal_brief: dict[str, Any],
    competitor_gap_brief: dict[str, Any],
    trace_id: str | None,
    lead_id: str | None,
) -> ToneClaimReviewRecord:
    review_id = f"review_{uuid4().hex[:12]}"
    issues, rewrites = _heuristic_screen(outbound)
    meta = outbound.metadata or {}
    tid = trace_id or "trace_reviewer"
    lid = lead_id or outbound.lead_id
    tool_results = run_reviewer_tool_sequence(
        policy=policy,
        outbound=outbound,
        hiring_signal_brief=hiring_signal_brief,
        competitor_gap_brief=competitor_gap_brief,
        trace_id=tid,
        lead_id=lid,
    )
    tool_issues = aggregate_tool_failures(tool_results)
    issues = [*issues, *tool_issues]
    by_tool = {r.tool: r for r in tool_results}
    if not by_tool.get("validate_claims", ReviewerToolResult(tool="validate_claims", passed=True, notes=[])).passed:
        return ToneClaimReviewRecord(
            review_id=review_id,
            draft_id=outbound.draft_id,
            status="rejected",
            issues=issues,
            required_rewrites=rewrites,
            final_send_ok=False,
        )
    if not by_tool.get(
        "redact_sensitive_content", ReviewerToolResult(tool="redact_sensitive_content", passed=True, notes=[])
    ).passed:
        return ToneClaimReviewRecord(
            review_id=review_id,
            draft_id=outbound.draft_id,
            status="rejected",
            issues=issues,
            required_rewrites=rewrites,
            final_send_ok=False,
        )

    decisions = [
        policy.check_kill_switch(trace_id=tid, lead_id=lid),
        policy.check_sink_routing(trace_id=tid, lead_id=lid),
        policy.check_claim_grounding(
            trace_id=tid,
            lead_id=lid,
            unsupported_claims=bool(meta.get("unsupported_claims", False)),
        ),
        policy.check_bench_commitment(
            trace_id=tid,
            lead_id=lid,
            message=f"{outbound.subject}\n{outbound.text_body or ''}",
            bench_verified=bool(meta.get("bench_verified", False)),
        ),
    ]
    blocked = next((d for d in decisions if d.decision != "pass"), None)
    if blocked:
        rec = ToneClaimReviewRecord(
            review_id=review_id,
            draft_id=outbound.draft_id,
            status="rejected",
            issues=[*issues, blocked.reason],
            required_rewrites=rewrites,
            final_send_ok=False,
        )
        log_trace_event(
            event_type="outreach_review_blocked",
            trace_id=trace_id or "trace_reviewer",
            lead_id=lead_id,
            status="blocked",
            payload=rec.model_dump(mode="json"),
        )
        return rec

    llm_out: ReviewerLLMOutput | None = None
    if llm is not None and llm.configured:
        user_payload = {
            "draft_subject": outbound.subject,
            "draft_body": outbound.text_body or "",
            "metadata": meta,
            "hiring_signal_brief_excerpt": json.dumps(hiring_signal_brief, default=str)[:6000],
            "competitor_gap_brief_excerpt": json.dumps(competitor_gap_brief, default=str)[:6000],
            "heuristic_and_tool_issues": issues,
        }
        raw = await llm.generate_model(
            system_prompt=_load_reviewer_system_prompt(),
            user_payload=user_payload,
            response_model=ReviewerLLMOutput,
            trace_id=trace_id,
            lead_id=lead_id,
            purpose="outreach.tone_claim_review",
        )
        llm_out = raw if isinstance(raw, ReviewerLLMOutput) else None

    if llm_out is not None:
        status = llm_out.status
        merged_issues = list({*issues, *llm_out.issues})
        merged_rw = list({*rewrites, *llm_out.required_rewrites})
        final_ok = llm_out.final_send_ok and status in {"approved", "approved_with_edits"}
        rec = ToneClaimReviewRecord(
            review_id=review_id,
            draft_id=outbound.draft_id,
            status=status,
            issues=merged_issues,
            required_rewrites=merged_rw,
            final_send_ok=final_ok,
        )
    else:
        if issues:
            rec = ToneClaimReviewRecord(
                review_id=review_id,
                draft_id=outbound.draft_id,
                status="pending",
                issues=issues,
                required_rewrites=rewrites,
                final_send_ok=False,
            )
        else:
            rec = ToneClaimReviewRecord(
                review_id=review_id,
                draft_id=outbound.draft_id,
                status="approved",
                issues=[],
                required_rewrites=[],
                final_send_ok=True,
            )

    log_processing_step(
        component="outreach.reviewer",
        step="review.complete",
        message="Tone/claim review finished",
        lead_id=lead_id,
        trace_id=trace_id,
        draft_id=outbound.draft_id,
        review_id=rec.review_id,
        status=rec.status,
        final_send_ok=rec.final_send_ok,
    )
    log_trace_event(
        event_type="outreach_review_record",
        trace_id=trace_id or "trace_reviewer",
        lead_id=lead_id,
        status="ok",
        payload={
            "review_id": rec.review_id,
            "draft_id": rec.draft_id,
            "status": rec.status,
            "issues": rec.issues,
            "evidence_refs": meta.get("grounded_claims"),
        },
    )
    return rec


def map_review_to_outbound_review_status(rec: ToneClaimReviewRecord) -> str:
    """Map reviewer status to OutboundEmailRequest.review_status literals."""
    if rec.status == "approved":
        return "approved"
    if rec.status == "approved_with_edits":
        return "approved_with_edits"
    if rec.status == "rejected":
        return "rejected"
    return "pending"
