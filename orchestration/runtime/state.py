"""WorkflowState — typed dict carried between LangGraph nodes.

LangGraph requires a single state schema for the whole graph. We use a
``TypedDict`` with ``total=False`` so each node can set its slice without
declaring every key. Reducers are explicit:

- ``findings`` and ``evidence_refs`` use list-append reducers
  (:func:`_append`).
- ``ai_tokens`` accumulates :class:`AITokenUsage`.
- ``errors`` appends non-fatal :class:`WorkflowError` entries.
- ``degraded`` uses logical-OR.

A node that mutates state returns ``{"key": value}`` dicts; LangGraph's
``Annotated[type, reducer]`` machinery folds them into the running state.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from core.llm.tokens import AITokenUsage
from agents.result import AgentResult


def _append_list(left: list, right: list) -> list:
    if not left:
        return list(right)
    if not right:
        return list(left)
    return list(left) + list(right)


def _accumulate_tokens(left: AITokenUsage, right: AITokenUsage) -> AITokenUsage:
    return left.add(right)


def _or_bool(left: bool, right: bool) -> bool:
    return left or right


def _last_write(left: Any, right: Any) -> Any:
    return right if right is not None else left


@dataclass(frozen=True)
class WorkflowError:
    node_name: str
    agent_name: str | None
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowState(TypedDict, total=False):
    workflow_run_id: Annotated[uuid.UUID, _last_write]
    investigation_id: Annotated[uuid.UUID | None, _last_write]
    correlation_id: Annotated[str | None, _last_write]
    workflow_name: Annotated[str, _last_write]

    inputs: Annotated[dict[str, Any], _last_write]
    options: Annotated[dict[str, Any], _last_write]

    # Slot-per-node — last-write-wins, since each node only writes its own slot.
    ingestion_result: Annotated[dict[str, Any] | None, _last_write]
    firewall_decision: Annotated[dict[str, Any] | None, _last_write]
    enrichment_result: Annotated[dict[str, Any] | None, _last_write]
    correlation_result: Annotated[dict[str, Any] | None, _last_write]
    reasoning_result: Annotated[dict[str, Any] | None, _last_write]
    integrity_result: Annotated[dict[str, Any] | None, _last_write]

    # Accumulators
    findings: Annotated[list[dict[str, Any]], _append_list]
    evidence_refs: Annotated[list[uuid.UUID], _append_list]
    agent_results: Annotated[list[dict[str, Any]], _append_list]
    ai_tokens: Annotated[AITokenUsage, _accumulate_tokens]
    errors: Annotated[list[WorkflowError], _append_list]

    # Flags
    degraded: Annotated[bool, _or_bool]
    final_state: Annotated[str | None, _last_write]
    last_node: Annotated[str | None, _last_write]


def new_workflow_state(
    *,
    workflow_run_id: uuid.UUID,
    workflow_name: str,
    inputs: dict[str, Any],
    options: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> WorkflowState:
    return WorkflowState(
        workflow_run_id=workflow_run_id,
        workflow_name=workflow_name,
        investigation_id=None,
        correlation_id=correlation_id,
        inputs=inputs,
        options=options or {},
        ingestion_result=None,
        firewall_decision=None,
        enrichment_result=None,
        correlation_result=None,
        reasoning_result=None,
        integrity_result=None,
        findings=[],
        evidence_refs=[],
        agent_results=[],
        ai_tokens=AITokenUsage(),
        errors=[],
        degraded=False,
        final_state=None,
        last_node=None,
    )


def record_agent_result(result: AgentResult) -> dict[str, Any]:
    """Render an :class:`AgentResult` into a small state-merge dict."""
    return {
        "agent_run_id": str(result.agent_run_id),
        "agent_name": result.agent_name,
        "status": result.status.value,
        "confidence": result.confidence,
        "duration_ms": result.duration_ms,
        "ai_tokens_input": result.ai_tokens.input,
        "ai_tokens_output": result.ai_tokens.output,
        "evidence_refs": [str(r) for r in result.evidence_refs],
        "error": result.error,
    }


def record_error(
    *, node_name: str, agent_name: str | None, reason: str
) -> WorkflowError:
    return WorkflowError(node_name=node_name, agent_name=agent_name, reason=reason)
