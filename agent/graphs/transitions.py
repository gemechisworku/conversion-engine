"""Lead lifecycle state transition validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvalidStateTransitionError(ValueError):
    from_state: str
    to_state: str

    def __str__(self) -> str:
        return f"Cannot transition from {self.from_state} to {self.to_state}."


_ALLOWED_TRANSITIONS: set[tuple[str, str]] = {
    ("new_lead", "enriching"),
    ("enriching", "brief_ready"),
    ("enriching", "disqualified"),
    ("enriching", "handoff_required"),
    ("brief_ready", "drafting"),
    ("drafting", "in_review"),
    ("in_review", "queued_to_send"),
    ("queued_to_send", "awaiting_reply"),
    ("awaiting_reply", "reply_received"),
    ("reply_received", "qualifying"),
    ("reply_received", "scheduling"),
    ("reply_received", "nurture"),
    ("reply_received", "disqualified"),
    ("reply_received", "handoff_required"),
    ("qualifying", "scheduling"),
    ("qualifying", "nurture"),
    ("qualifying", "awaiting_reply"),
    ("scheduling", "awaiting_reply"),
    ("scheduling", "booked"),
    ("scheduling", "handoff_required"),
    ("booked", "closed"),
}

_TERMINAL_STATES: set[str] = {"closed", "disqualified"}


def validate_lead_transition(*, from_state: str, to_state: str) -> None:
    if from_state == to_state:
        return
    if from_state in _TERMINAL_STATES:
        raise InvalidStateTransitionError(from_state=from_state, to_state=to_state)
    if to_state in {"handoff_required", "disqualified"}:
        return
    if (from_state, to_state) not in _ALLOWED_TRANSITIONS:
        raise InvalidStateTransitionError(from_state=from_state, to_state=to_state)


def is_transition_allowed(*, from_state: str, to_state: str) -> bool:
    try:
        validate_lead_transition(from_state=from_state, to_state=to_state)
    except InvalidStateTransitionError:
        return False
    return True

