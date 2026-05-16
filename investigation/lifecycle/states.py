"""Investigation lifecycle FSM.

Exactly mirrors PLAN.md §6. ``FAILED`` is reachable from every non-terminal
state; ``ARCHIVED`` only from ``COMPLETED``; ``FAILED`` and ``ARCHIVED`` are
terminal.

Phase 2 only exercises CREATED → ENRICHING → COMPLETED (or → REVIEW_REQUIRED).
CORRELATING / ANALYZING are defined now but only reachable from Phase 3+ flows.
"""
from __future__ import annotations

from enum import Enum


class InvestigationState(str, Enum):
    CREATED = "CREATED"
    ENRICHING = "ENRICHING"
    CORRELATING = "CORRELATING"
    ANALYZING = "ANALYZING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


_S = InvestigationState

ALLOWED_TRANSITIONS: dict[InvestigationState, frozenset[InvestigationState]] = {
    _S.CREATED: frozenset({_S.ENRICHING, _S.FAILED}),
    _S.ENRICHING: frozenset({_S.CORRELATING, _S.REVIEW_REQUIRED, _S.COMPLETED, _S.FAILED}),
    _S.CORRELATING: frozenset({_S.ANALYZING, _S.REVIEW_REQUIRED, _S.COMPLETED, _S.FAILED}),
    _S.ANALYZING: frozenset({_S.REVIEW_REQUIRED, _S.COMPLETED, _S.FAILED}),
    _S.REVIEW_REQUIRED: frozenset({_S.ANALYZING, _S.COMPLETED, _S.FAILED}),
    _S.COMPLETED: frozenset({_S.ARCHIVED}),
    _S.ARCHIVED: frozenset(),
    _S.FAILED: frozenset(),
}


def is_valid_transition(current: InvestigationState, target: InvestigationState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())
