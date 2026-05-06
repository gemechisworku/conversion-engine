"""Shared reply intent → next action → session stage mapping (reply_handling.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Implements: FR-9
# Workflow: reply_handling.md
# Schema: conversation_state.md


@dataclass(frozen=True)
class ReplyTextSignals:
    """Heuristic multi-signal view of inbound text (scaffolding; not a substitute for LLM)."""

    has_schedule_cue: bool
    has_question: bool
    has_explain_or_clarify_cue: bool
    has_objection_cue: bool
    has_interest_cue: bool
    has_decline_cue: bool
    has_concrete_time_cue: bool
    has_vague_time_cue: bool


_SCHEDULE_TOKENS = (
    "book",
    "schedule",
    "calendar",
    "time",
    "zoom",
    "meet ",
    "meeting",
    "call next",
    "availability",
    "tomorrow",
    "today",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    " pm",
    " am",
    "p.m",
    "a.m",
    "o'clock",
    "oclock",
    " eat",
    " est",
    " pst",
    " cst",
    " mst",
    " gmt",
    " utc",
)

_VAGUE_TIME_PHRASES = (
    "next week",
    "next month",
    "sometime",
    "soon",
    "whenever",
    "flexible",
    "later this week",
    "early next week",
)

_EXPLAIN_CLARIFY_TOKENS = (
    "explain",
    "clarify",
    "what about",
    "does this",
    "does it",
    "include ",
    "onboarding",
)

# "?" with these phrases is treated as scheduling logistics, not product clarification.
def _is_requesting_availability_options(lowered: str) -> bool:
    """Prospect asks us for slots / availability — not underspecified acceptance of a meeting."""
    return any(
        p in lowered
        for p in (
            "available times",
            "availability",
            "send me times",
            "share times",
            "share available",
            "what times",
            "what time works",
            "slots",
            "calendar link",
            "cal.com",
            "book a time",
            "pick a time",
        )
    )


_SCHEDULING_LOGISTICS_PHRASES = (
    "can we book",
    "could we book",
    "could we schedule",
    "can we schedule",
    "would you be free",
    "are you free",
    "what time",
    "which day",
    "which slot",
    "what works for you",
    "does next",
    "does tuesday",
    "does monday",
    "share available",
    "available times",
    "send availability",
    "your availability",
)


def extract_reply_text_signals(content: str) -> ReplyTextSignals:
    """Extract overlapping cues from inbound text for boundary ratification."""
    lowered = content.lower()
    has_schedule_cue = any(token in lowered for token in _SCHEDULE_TOKENS)
    has_question = "?" in content
    has_explain_or_clarify_cue = any(tok in lowered for tok in _EXPLAIN_CLARIFY_TOKENS)
    has_objection_cue = any(token in lowered for token in ("price", "cost", "quote", "proposal"))
    has_interest_cue = any(
        token in lowered
        for token in ("yes", "interested", "sounds good", "works for me", "that works")
    )
    has_decline_cue = any(token in lowered for token in ("not interested", "stop", "no thanks", "unsubscribe"))
    has_vague_time_cue = any(phrase in lowered for phrase in _VAGUE_TIME_PHRASES)
    # Concrete enough to treat scheduling as plausibly executable (heuristic).
    weekday_re = (
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today)\b"
    )
    has_weekday_or_day = bool(re.search(weekday_re, lowered, re.I))
    has_tod_window = any(w in lowered for w in ("morning", "afternoon", "evening", "noon"))
    has_concrete_time_cue = bool(
        re.search(r"\b\d{1,2}\s*:\s*\d{2}\s*(am|pm|a\.m|p\.m)\b", lowered, re.I)
        or re.search(r"\b\d{1,2}\s*(am|pm|a\.m|p\.m)\b", lowered, re.I)
        or re.search(
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.+"
            r"\b\d{1,2}\s*(am|pm|a\.m|p\.m|:)\b",
            lowered,
            re.I,
        )
        or re.search(r"\b(tomorrow|today)\b.+\b\d{1,2}\b", lowered, re.I)
        or (has_weekday_or_day and has_tod_window)
        or (has_weekday_or_day and re.search(r"\b\d{1,2}\b", lowered))
    )
    return ReplyTextSignals(
        has_schedule_cue=has_schedule_cue,
        has_question=has_question,
        has_explain_or_clarify_cue=has_explain_or_clarify_cue,
        has_objection_cue=has_objection_cue,
        has_interest_cue=has_interest_cue,
        has_decline_cue=has_decline_cue,
        has_concrete_time_cue=has_concrete_time_cue,
        has_vague_time_cue=has_vague_time_cue,
    )


def _mixed_schedule_clarify(s: ReplyTextSignals, lowered: str) -> bool:
    """Product/scope clarification layered on acceptance or scheduling — dual-track arbitration."""
    scope_clarify = s.has_explain_or_clarify_cue
    logistics_q = any(p in lowered for p in _SCHEDULING_LOGISTICS_PHRASES)
    question_is_scope = s.has_question and not logistics_q
    if not (scope_clarify or question_is_scope):
        return False
    return s.has_schedule_cue or s.has_interest_cue


def _schedule_underspecified(s: ReplyTextSignals, lowered: str) -> bool:
    """Acceptance / time language without an executable slot — do not commit to booking path."""
    if _is_requesting_availability_options(lowered):
        return False
    if s.has_concrete_time_cue:
        return False
    if s.has_vague_time_cue and (s.has_schedule_cue or s.has_interest_cue):
        return True
    # Schedule cue (e.g. "let's meet") but no concrete window in text
    if s.has_schedule_cue and not s.has_concrete_time_cue and not s.has_question:
        return True
    return False


def classify_intent_from_text(content: str) -> str:
    """Single-label intent for logging; prefers multi-intent / underspecified labels when detected."""
    lowered = content.lower()
    signals = extract_reply_text_signals(content)

    if signals.has_decline_cue:
        return "decline"
    if signals.has_objection_cue:
        return "objection"
    if _mixed_schedule_clarify(signals, lowered):
        return "mixed_schedule_clarify"
    if _schedule_underspecified(signals, lowered):
        return "schedule_underspecified"
    if any(token in lowered for token in _SCHEDULE_TOKENS):
        return "schedule"
    if "?" in lowered:
        return "clarification"
    if any(token in lowered for token in ("yes", "interested", "sounds good")):
        return "interest"
    return "unclear"


def next_action_for_intent(intent: str) -> str:
    mapping = {
        "schedule": "schedule",
        "interest": "qualify",
        "clarification": "clarify",
        "objection": "handle_objection",
        "decline": "nurture",
        "unclear": "clarify",
        "mixed_schedule_clarify": "clarify",
        "schedule_underspecified": "clarify",
    }
    return mapping.get(intent, "clarify")


def session_stage_for_next_action(next_action: str) -> str:
    if next_action == "escalate":
        return "handoff_required"
    if next_action == "schedule":
        return "scheduling"
    if next_action == "nurture":
        return "nurture"
    return "qualifying"


def default_branch_playbook(
    next_action: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Default (single-track) playbook per next_action."""
    playbooks: dict[str, tuple[str, list[dict[str, Any]]]] = {
        "schedule": (
            "schedule",
            [{"action_type": "delegate_scheduler", "status": "pending", "branch": "schedule"}],
        ),
        "qualify": (
            "interest",
            [{"action_type": "continue_qualification", "status": "pending", "branch": "interest"}],
        ),
        "clarify": (
            "clarify",
            [{"action_type": "answer_clarification", "status": "pending", "branch": "clarify"}],
        ),
        "handle_objection": (
            "objection",
            [{"action_type": "handle_objection", "status": "pending", "branch": "objection"}],
        ),
        "nurture": ("decline", [{"action_type": "nurture", "status": "pending", "branch": "decline"}]),
        "escalate": (
            "escalate",
            [{"action_type": "escalate", "status": "pending", "branch": "escalate"}],
        ),
    }
    return playbooks.get(next_action, playbooks["clarify"])


def ratify_reply_route(
    *,
    combined_text: str,
    intent: str,
    next_action: str,
    email_interp: dict[str, Any] | None,
) -> tuple[str, dict[str, Any], tuple[str, list[dict[str, Any]]] | None]:
    """
    Scaffolding ratification: model proposes; deterministic rules gate high-risk paths.

    Returns (ratified_next_action, routing_flags, optional_playbook_override).
    When playbook override is None, callers should use default_branch_playbook(ratified_next_action).
    """
    flags: dict[str, Any] = {
        "original_next_action": next_action,
        "original_intent": intent,
        "ratified": False,
        "reason": None,
    }
    lowered_ct = combined_text.lower()
    signals = extract_reply_text_signals(combined_text)
    ratified = next_action
    override: tuple[str, list[dict[str, Any]]] | None = None

    if email_interp:
        completeness = str(email_interp.get("scheduling_completeness") or "not_applicable")
        has_clar = bool(email_interp.get("has_clarification_request"))
        if next_action == "schedule":
            if has_clar:
                ratified = "clarify"
                flags["ratified"] = True
                flags["reason"] = "schedule_with_clarification_dual_track"
                override = (
                    "clarify",
                    [
                        {"action_type": "answer_clarification", "status": "pending", "branch": "clarify"},
                        {
                            "action_type": "delegate_scheduler",
                            "status": "pending",
                            "branch": "schedule",
                            "note": "resume_after_clarification",
                        },
                    ],
                )
            elif completeness == "accepted_incomplete":
                # LLM may label "share available times next week" as incomplete; heuristically it is a scheduling request.
                if _is_requesting_availability_options(lowered_ct):
                    flags["reason"] = "availability_request_preserve_schedule"
                    return ratified, flags, None
                ratified = "clarify"
                flags["ratified"] = True
                flags["reason"] = "accepted_incomplete_no_executable_slot"
                override = (
                    "clarify",
                    [
                        {
                            "action_type": "clarify_scheduling_slot",
                            "status": "pending",
                            "branch": "clarify",
                            "note": "need_concrete_day_time_timezone",
                        },
                        {
                            "action_type": "delegate_scheduler",
                            "status": "pending",
                            "branch": "schedule",
                            "note": "after_slot_confirmed",
                        },
                    ],
                )
        return ratified, flags, override

    # Heuristic-only path (no LLM interpretation dict)
    if ratified == "schedule":
        if _mixed_schedule_clarify(signals, lowered_ct):
            ratified = "clarify"
            flags["ratified"] = True
            flags["reason"] = "heuristic_mixed_schedule_clarify"
            override = (
                "clarify",
                [
                    {"action_type": "answer_clarification", "status": "pending", "branch": "clarify"},
                    {
                        "action_type": "delegate_scheduler",
                        "status": "pending",
                        "branch": "schedule",
                        "note": "resume_after_clarification",
                    },
                ],
            )
        elif _schedule_underspecified(signals, lowered_ct):
            ratified = "clarify"
            flags["ratified"] = True
            flags["reason"] = "heuristic_schedule_underspecified"
            override = (
                "clarify",
                [
                    {
                        "action_type": "clarify_scheduling_slot",
                        "status": "pending",
                        "branch": "clarify",
                        "note": "need_concrete_day_time_timezone",
                    },
                    {
                        "action_type": "delegate_scheduler",
                        "status": "pending",
                        "branch": "schedule",
                        "note": "after_slot_confirmed",
                    },
                ],
            )

    if intent == "mixed_schedule_clarify" and override is None:
        ratified = "clarify"
        flags["ratified"] = True
        flags["reason"] = flags.get("reason") or "intent_mixed_schedule_clarify"
        override = (
            "clarify",
            [
                {"action_type": "answer_clarification", "status": "pending", "branch": "clarify"},
                {
                    "action_type": "delegate_scheduler",
                    "status": "pending",
                    "branch": "schedule",
                    "note": "resume_after_clarification",
                },
            ],
        )
    if intent == "schedule_underspecified" and override is None:
        ratified = "clarify"
        flags["ratified"] = True
        flags["reason"] = flags.get("reason") or "intent_schedule_underspecified"
        override = (
            "clarify",
            [
                {
                    "action_type": "clarify_scheduling_slot",
                    "status": "pending",
                    "branch": "clarify",
                    "note": "need_concrete_day_time_timezone",
                },
                {
                    "action_type": "delegate_scheduler",
                    "status": "pending",
                    "branch": "schedule",
                    "note": "after_slot_confirmed",
                },
            ],
        )

    return ratified, flags, override
