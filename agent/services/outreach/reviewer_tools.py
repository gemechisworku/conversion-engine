"""Reviewer tool loop (tone_and_claim_reviewer_spec.md §3) — delegates to policy + lightweight checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent.services.email.schemas import OutboundEmailRequest
from agent.services.observability.events import log_processing_step
from agent.services.policy.outbound_policy import OutboundPolicyService


@dataclass
class ReviewerToolResult:
    tool: str
    passed: bool
    notes: list[str]


def _validate_claims(
    *,
    outbound: OutboundEmailRequest,
    hiring_signal_brief: dict[str, Any],
    competitor_gap_brief: dict[str, Any],
) -> ReviewerToolResult:
    """validate_claims — surface unsupported_claims flag and empty brief guard."""
    notes: list[str] = []
    meta = outbound.metadata or {}
    if meta.get("unsupported_claims"):
        notes.append("metadata_unsupported_claims_true")
    if not hiring_signal_brief and not competitor_gap_brief:
        notes.append("no_brief_context_for_grounding")
    passed = not bool(meta.get("unsupported_claims", False))
    return ReviewerToolResult(tool="validate_claims", passed=passed, notes=notes)


def _check_bench_commitment(
    *,
    policy: OutboundPolicyService,
    outbound: OutboundEmailRequest,
    trace_id: str,
    lead_id: str,
) -> ReviewerToolResult:
    meta = outbound.metadata or {}
    d = policy.check_bench_commitment(
        trace_id=trace_id,
        lead_id=lead_id,
        message=f"{outbound.subject}\n{outbound.text_body or ''}",
        bench_verified=bool(meta.get("bench_verified", False)),
    )
    ok = d.decision == "pass"
    return ReviewerToolResult(
        tool="check_bench_commitment",
        passed=ok,
        notes=[] if ok else [d.reason],
    )


def _redact_sensitive_content(*, outbound: OutboundEmailRequest) -> ReviewerToolResult:
    """redact_sensitive_content — detect likely secrets; do not mutate draft here (orchestrator may redact)."""
    body = outbound.text_body or ""
    notes = []
    if re.search(r"\b(sk_live_|pk_live_|Bearer\s+[A-Za-z0-9\-_]{20,})\b", body):
        notes.append("possible_secret_pattern_in_body")
    return ReviewerToolResult(tool="redact_sensitive_content", passed=len(notes) == 0, notes=notes)


def _kb_read_page_stub(*, hiring_signal_brief: dict[str, Any]) -> ReviewerToolResult:
    """kb_read_page — no KB integration; use brief excerpt only (stub)."""
    has = bool(hiring_signal_brief)
    return ReviewerToolResult(
        tool="kb_read_page",
        passed=has,
        notes=[] if has else ["kb_stub_no_hiring_brief"],
    )


def run_reviewer_tool_sequence(
    *,
    policy: OutboundPolicyService,
    outbound: OutboundEmailRequest,
    hiring_signal_brief: dict[str, Any],
    competitor_gap_brief: dict[str, Any],
    trace_id: str,
    lead_id: str,
) -> list[ReviewerToolResult]:
    """Ordered tool loop before LLM adjudication."""
    results = [
        _validate_claims(
            outbound=outbound,
            hiring_signal_brief=hiring_signal_brief,
            competitor_gap_brief=competitor_gap_brief,
        ),
        _check_bench_commitment(policy=policy, outbound=outbound, trace_id=trace_id, lead_id=lead_id),
        _redact_sensitive_content(outbound=outbound),
        _kb_read_page_stub(hiring_signal_brief=hiring_signal_brief),
    ]
    for r in results:
        log_processing_step(
            component="outreach.reviewer_tools",
            step=f"tool.{r.tool}",
            message="Reviewer tool step",
            trace_id=trace_id,
            lead_id=lead_id,
            tool=r.tool,
            passed=r.passed,
            notes=r.notes,
        )
    return results


def aggregate_tool_failures(results: list[ReviewerToolResult]) -> list[str]:
    issues: list[str] = []
    for r in results:
        if not r.passed:
            issues.extend([f"{r.tool}:{n}" for n in r.notes] or [f"{r.tool}:failed"])
    return issues
