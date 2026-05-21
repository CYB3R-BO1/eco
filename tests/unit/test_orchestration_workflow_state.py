"""WorkflowState helpers + FSM transitions."""
from __future__ import annotations

import uuid

from core.llm.tokens import AITokenUsage
from orchestration.runtime.state import (
    new_workflow_state,
    record_agent_result,
    record_error,
)
from orchestration.workflows.states import (
    WorkflowRunStatus,
    is_valid_workflow_transition,
)
from agents.result import AgentResult, AgentRunStatus


def test_new_state_has_expected_keys() -> None:
    state = new_workflow_state(
        workflow_run_id=uuid.uuid4(),
        workflow_name="investigation",
        inputs={"payload": "8.8.8.8"},
    )
    assert state["workflow_name"] == "investigation"
    assert state["findings"] == []
    assert state["evidence_refs"] == []
    assert state["ai_tokens"] == AITokenUsage()
    assert state["degraded"] is False


def test_record_agent_result_shape() -> None:
    result = AgentResult(
        agent_run_id=uuid.uuid4(),
        agent_name="enrichment",
        status=AgentRunStatus.SUCCESS,
        evidence_refs=[uuid.uuid4()],
        confidence=0.9,
        duration_ms=125,
    )
    rendered = record_agent_result(result)
    assert rendered["agent_name"] == "enrichment"
    assert rendered["status"] == "SUCCESS"
    assert rendered["confidence"] == 0.9
    assert rendered["duration_ms"] == 125
    assert isinstance(rendered["agent_run_id"], str)


def test_record_error_holds_node_and_reason() -> None:
    err = record_error(
        node_name="enrichment", agent_name="enrichment", reason="no providers"
    )
    assert err.node_name == "enrichment"
    assert err.agent_name == "enrichment"
    assert err.reason == "no providers"
    assert err.occurred_at is not None


def test_valid_transitions() -> None:
    assert is_valid_workflow_transition(
        WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING
    )
    assert is_valid_workflow_transition(
        WorkflowRunStatus.RUNNING, WorkflowRunStatus.SUCCEEDED
    )
    assert is_valid_workflow_transition(
        WorkflowRunStatus.RUNNING, WorkflowRunStatus.REVIEW_REQUIRED
    )
    assert is_valid_workflow_transition(
        WorkflowRunStatus.RUNNING, WorkflowRunStatus.FAILED
    )


def test_invalid_transitions() -> None:
    # Terminal states allow nothing.
    assert not is_valid_workflow_transition(
        WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.RUNNING
    )
    assert not is_valid_workflow_transition(
        WorkflowRunStatus.FAILED, WorkflowRunStatus.SUCCEEDED
    )
    # Can't skip from PENDING to a terminal that isn't FAILED.
    assert not is_valid_workflow_transition(
        WorkflowRunStatus.PENDING, WorkflowRunStatus.SUCCEEDED
    )
