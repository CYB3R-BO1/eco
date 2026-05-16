from __future__ import annotations

from investigation.lifecycle.states import (
    ALLOWED_TRANSITIONS,
    InvestigationState,
    is_valid_transition,
)


def test_initial_state_to_enriching_allowed() -> None:
    assert is_valid_transition(InvestigationState.CREATED, InvestigationState.ENRICHING)


def test_skip_to_completed_disallowed_from_created() -> None:
    assert not is_valid_transition(InvestigationState.CREATED, InvestigationState.COMPLETED)


def test_failed_reachable_from_every_active_state() -> None:
    for state in InvestigationState:
        if state in {InvestigationState.FAILED, InvestigationState.ARCHIVED}:
            continue
        assert InvestigationState.FAILED in ALLOWED_TRANSITIONS[state], state


def test_archived_only_from_completed() -> None:
    for state in InvestigationState:
        is_allowed = InvestigationState.ARCHIVED in ALLOWED_TRANSITIONS.get(state, frozenset())
        assert is_allowed == (state is InvestigationState.COMPLETED), state


def test_terminal_states_have_no_outgoing_transitions() -> None:
    assert ALLOWED_TRANSITIONS[InvestigationState.FAILED] == frozenset()
    assert ALLOWED_TRANSITIONS[InvestigationState.ARCHIVED] == frozenset()


def test_phase2_happy_path() -> None:
    """CREATED → ENRICHING → COMPLETED should be a valid Phase 2 sequence."""
    assert is_valid_transition(InvestigationState.CREATED, InvestigationState.ENRICHING)
    assert is_valid_transition(InvestigationState.ENRICHING, InvestigationState.COMPLETED)
