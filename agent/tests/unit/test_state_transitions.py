from __future__ import annotations

import pytest

from agent.graphs.transitions import InvalidStateTransitionError, is_transition_allowed, validate_lead_transition


def test_valid_transition_passes() -> None:
    validate_lead_transition(from_state="new_lead", to_state="enriching")
    validate_lead_transition(from_state="awaiting_reply", to_state="reply_received")


def test_invalid_transition_raises() -> None:
    with pytest.raises(InvalidStateTransitionError):
        validate_lead_transition(from_state="awaiting_reply", to_state="booked")


def test_terminal_state_cannot_reopen() -> None:
    with pytest.raises(InvalidStateTransitionError):
        validate_lead_transition(from_state="closed", to_state="drafting")


def test_is_transition_allowed() -> None:
    assert is_transition_allowed(from_state="qualifying", to_state="scheduling") is True
    assert is_transition_allowed(from_state="disqualified", to_state="queued_to_send") is False

