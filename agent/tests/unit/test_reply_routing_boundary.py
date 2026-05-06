from __future__ import annotations

from agent.graphs.reply_routing import (
    classify_intent_from_text,
    extract_reply_text_signals,
    next_action_for_intent,
    ratify_reply_route,
)


def test_mixed_acceptance_and_question_intent() -> None:
    text = "That works for me. Can you explain whether onboarding support is included?"
    assert classify_intent_from_text(text) == "mixed_schedule_clarify"
    assert next_action_for_intent("mixed_schedule_clarify") == "clarify"


def test_underspecified_next_week() -> None:
    text = "Yes, let's do it next week."
    assert classify_intent_from_text(text) == "schedule_underspecified"


def test_ratify_heuristic_mixed_dual_playbook() -> None:
    text = "What is the cost per seat for your team?"
    intent = classify_intent_from_text(text)
    assert intent == "objection"
    na = next_action_for_intent(intent)
    r, flags, override = ratify_reply_route(combined_text=text, intent=intent, next_action=na, email_interp=None)
    assert r == "handle_objection"
    assert override is None


def test_ratify_llm_schedule_incomplete() -> None:
    interp = {
        "next_best_action": "schedule",
        "scheduling_completeness": "accepted_incomplete",
        "has_clarification_request": False,
    }
    r, flags, override = ratify_reply_route(
        combined_text="anything",
        intent="schedule",
        next_action="schedule",
        email_interp=interp,
    )
    assert r == "clarify"
    assert flags["ratified"] is True
    assert override is not None
    assert override[0] == "clarify"
    assert len(override[1]) == 2


def test_ratify_llm_schedule_with_clarification_dual() -> None:
    interp = {
        "next_best_action": "schedule",
        "scheduling_completeness": "executable",
        "has_clarification_request": True,
    }
    r, flags, override = ratify_reply_route(
        combined_text="x",
        intent="schedule",
        next_action="schedule",
        email_interp=interp,
    )
    assert r == "clarify"
    assert flags["reason"] == "schedule_with_clarification_dual_track"
    assert override is not None
    types = [p["action_type"] for p in override[1]]
    assert "answer_clarification" in types
    assert "delegate_scheduler" in types


def test_concrete_tuesday_afternoon_not_underspecified() -> None:
    text = "Can we book time next Tuesday afternoon?"
    s = extract_reply_text_signals(text)
    assert s.has_concrete_time_cue is True
    assert classify_intent_from_text(text) == "schedule"
