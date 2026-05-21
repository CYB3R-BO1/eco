"""Workflow run FSM.

Separate from ``InvestigationState`` (investigation/lifecycle/states.py) —
this tracks the *workflow execution*, not the investigation. A single
workflow run can advance an investigation through multiple states.

Terminal states: SUCCEEDED, REVIEW_REQUIRED, FAILED.
"""
from __future__ import annotations

from enum import Enum


class WorkflowRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


_W = WorkflowRunStatus

ALLOWED_WORKFLOW_TRANSITIONS: dict[WorkflowRunStatus, frozenset[WorkflowRunStatus]] = {
    _W.PENDING: frozenset({_W.RUNNING, _W.FAILED}),
    _W.RUNNING: frozenset({_W.SUCCEEDED, _W.REVIEW_REQUIRED, _W.FAILED}),
    _W.SUCCEEDED: frozenset(),
    _W.REVIEW_REQUIRED: frozenset(),
    _W.FAILED: frozenset(),
}


def is_valid_workflow_transition(
    current: WorkflowRunStatus, target: WorkflowRunStatus
) -> bool:
    return target in ALLOWED_WORKFLOW_TRANSITIONS.get(current, frozenset())
