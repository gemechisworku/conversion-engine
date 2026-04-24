"""Shared reply intent → next action → session stage mapping (reply_handling.md)."""

from __future__ import annotations


def classify_intent_from_text(content: str) -> str:
    lowered = content.lower()
    if any(token in lowered for token in ("book", "schedule", "calendar", "time")):
        return "schedule"
    if any(token in lowered for token in ("not interested", "stop", "no thanks", "unsubscribe")):
        return "decline"
    if any(token in lowered for token in ("price", "cost", "quote", "proposal")):
        return "objection"
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
