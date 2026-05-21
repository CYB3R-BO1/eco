"""Investigation workflow.

LangGraph DAG (PLAN.md §7):

::

    START → ingest_node → enrichment_node → correlation_node
            → (branch on degraded) →
              reasoning_node → finalize_node → END
                              ↘
                                finalize_node → END

``ingest_node`` wraps :meth:`IngestionPipeline.ingest` as a **single
opaque node** (per the wrap-don't-decompose user decision in plan mode).
We do **not** invoke the background ``_process`` flow — we run the
deterministic steps here (extraction → enrichment → correlation) as
LangGraph nodes via the four agents, so the workflow has visible
checkpoints between each step.

Every node returns a state-merge dict (LangGraph reducers fold it into
the running state). Nodes never raise — they catch and record errors so
the graph always advances; failure is signalled via ``degraded=True`` or
a non-``SUCCESS`` agent status in ``agent_results``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from agents.context import AgentExecutionContext
from agents.enrichment.agent import EnrichmentAgent
from agents.ioc_correlation.agent import IOCCorrelationAgent
from agents.reasoning.agent import ReasoningAgent
from agents.result import AgentRunStatus
from core.cache.redis import RedisClient
from core.config.settings import OrchestrationSettings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.events.types import EventType
from core.llm.budget import InvestigationTokenBudget
from core.llm.client import LLMClient
from evidence.store import EvidenceStore
from investigation.ingestion.pipeline import IngestionPipeline
from investigation.lifecycle.manager import LifecycleManager
from investigation.lifecycle.states import InvestigationState
from orchestration.memory.audit import MemoryAuditLogger
from orchestration.memory.store import InvestigationMemory
from orchestration.retry.circuit_breaker import CircuitBreakerRegistry
from orchestration.retry.policies import DEFAULT_AI_POLICY, DEFAULT_ENRICHMENT_POLICY
from orchestration.runtime.state import (
    WorkflowState,
    record_agent_result,
    record_error,
)
from resolution.types import EntityType
from storage.postgres.models.investigation import Investigation

log = structlog.get_logger(__name__)


@dataclass
class InvestigationWorkflowDeps:
    """All collaborators a workflow node needs.

    Built once at app startup; passed into :func:`build_investigation_graph`
    which closes over it. This keeps each node a closure (one positional
    ``state`` arg) which is what LangGraph expects.
    """

    settings: OrchestrationSettings
    database: Database
    redis: RedisClient
    event_emitter: EventEmitter
    evidence_store: EvidenceStore
    lifecycle_manager: LifecycleManager
    llm: LLMClient
    token_budget: InvestigationTokenBudget
    circuit_breakers: CircuitBreakerRegistry
    memory_audit: MemoryAuditLogger
    ingestion_pipeline: IngestionPipeline
    enrichment_agent: EnrichmentAgent
    correlation_agent: IOCCorrelationAgent
    reasoning_agent: ReasoningAgent


def build_investigation_graph(deps: InvestigationWorkflowDeps, *, checkpointer):
    """Build & compile the investigation workflow graph.

    Imported lazily so that LangGraph is not required to import this
    module (e.g. for static analysis).
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkflowState)
    graph.add_node("ingest", _make_ingest_node(deps))
    graph.add_node("enrichment", _make_enrichment_node(deps))
    graph.add_node("correlation", _make_correlation_node(deps))
    graph.add_node("reasoning", _make_reasoning_node(deps))
    graph.add_node("finalize", _make_finalize_node(deps))

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "enrichment")
    graph.add_edge("enrichment", "correlation")
    graph.add_conditional_edges(
        "correlation",
        _route_after_correlation,
        {"reasoning": "reasoning", "finalize": "finalize"},
    )
    graph.add_edge("reasoning", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------
def _make_ingest_node(deps: InvestigationWorkflowDeps):
    async def ingest_node(state: WorkflowState) -> dict[str, Any]:
        inputs = state.get("inputs") or {}
        artifact = inputs.get("payload")
        declared = inputs.get("declared_type")
        declared_type = EntityType(declared) if declared else None
        source_hint = inputs.get("source_hint")
        idempotency_key = inputs.get("idempotency_key")

        try:
            result = await deps.ingestion_pipeline.ingest(
                artifact,
                declared_type=declared_type,
                source_hint=source_hint,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            log.exception("workflow.ingest_failed")
            return {
                "errors": [
                    record_error(
                        node_name="ingest",
                        agent_name=None,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                ],
                "degraded": True,
                "last_node": "ingest",
                "final_state": "FAILED",
            }

        return {
            "investigation_id": result.investigation_id,
            "ingestion_result": {
                "investigation_id": str(result.investigation_id),
                "evidence_id": str(result.evidence_id),
                "status": result.status,
            },
            "evidence_refs": [result.evidence_id],
            "last_node": "ingest",
        }

    return ingest_node


def _make_enrichment_node(deps: InvestigationWorkflowDeps):
    async def enrichment_node(state: WorkflowState) -> dict[str, Any]:
        investigation_id = state.get("investigation_id")
        if investigation_id is None:
            return {
                "errors": [
                    record_error(
                        node_name="enrichment",
                        agent_name="enrichment",
                        reason="missing investigation_id",
                    )
                ],
                "degraded": True,
                "last_node": "enrichment",
            }

        # Transition to ENRICHING (idempotent if already there).
        try:
            async with deps.database.session() as session:
                await deps.lifecycle_manager.transition(
                    session,
                    investigation_id,
                    InvestigationState.ENRICHING,
                    reason="orchestration: entering enrichment",
                )
                await session.commit()
        except Exception:
            log.debug("workflow.enrichment.transition_skipped", investigation_id=str(investigation_id))

        ctx = _build_ctx(
            deps,
            state,
            agent_run_id=uuid.uuid4(),
            node_name="enrichment",
            policy=DEFAULT_ENRICHMENT_POLICY,
        )
        result = await deps.enrichment_agent.execute(ctx)
        return {
            "enrichment_result": {
                "status": result.status.value,
                "findings": result.findings,
                "duration_ms": result.duration_ms,
            },
            "findings": result.findings,
            "evidence_refs": list(result.evidence_refs),
            "agent_results": [record_agent_result(result)],
            "ai_tokens": result.ai_tokens,
            "degraded": result.status != AgentRunStatus.SUCCESS,
            "last_node": "enrichment",
        }

    return enrichment_node


def _make_correlation_node(deps: InvestigationWorkflowDeps):
    async def correlation_node(state: WorkflowState) -> dict[str, Any]:
        investigation_id = state.get("investigation_id")
        if investigation_id is None:
            return {
                "errors": [
                    record_error(
                        node_name="correlation",
                        agent_name="ioc_correlation",
                        reason="missing investigation_id",
                    )
                ],
                "degraded": True,
                "last_node": "correlation",
            }

        try:
            async with deps.database.session() as session:
                await deps.lifecycle_manager.transition(
                    session,
                    investigation_id,
                    InvestigationState.CORRELATING,
                    reason="orchestration: entering correlation",
                )
                await session.commit()
        except Exception:
            log.debug("workflow.correlation.transition_skipped")

        ctx = _build_ctx(
            deps,
            state,
            agent_run_id=uuid.uuid4(),
            node_name="correlation",
            policy=DEFAULT_ENRICHMENT_POLICY,
        )
        result = await deps.correlation_agent.execute(ctx)
        return {
            "correlation_result": {
                "status": result.status.value,
                "findings": result.findings,
                "duration_ms": result.duration_ms,
            },
            "findings": result.findings,
            "agent_results": [record_agent_result(result)],
            "degraded": result.status != AgentRunStatus.SUCCESS,
            "last_node": "correlation",
        }

    return correlation_node


def _make_reasoning_node(deps: InvestigationWorkflowDeps):
    async def reasoning_node(state: WorkflowState) -> dict[str, Any]:
        investigation_id = state.get("investigation_id")
        if investigation_id is None:
            return {"last_node": "reasoning"}

        try:
            async with deps.database.session() as session:
                await deps.lifecycle_manager.transition(
                    session,
                    investigation_id,
                    InvestigationState.ANALYZING,
                    reason="orchestration: reasoning",
                )
                await session.commit()
        except Exception:
            log.debug("workflow.reasoning.transition_skipped")

        ctx = _build_ctx(
            deps,
            state,
            agent_run_id=uuid.uuid4(),
            node_name="reasoning",
            policy=DEFAULT_AI_POLICY,
            inputs_extra={"findings": state.get("findings") or []},
        )
        result = await deps.reasoning_agent.execute(ctx)
        is_degraded = result.status in {
            AgentRunStatus.DEGRADED,
            AgentRunStatus.AI_UNAVAILABLE,
            AgentRunStatus.TIMEOUT,
            AgentRunStatus.FAILED,
        }
        return {
            "reasoning_result": {
                "status": result.status.value,
                "findings": result.findings,
                "duration_ms": result.duration_ms,
                "ai_tokens": result.ai_tokens.to_dict(),
            },
            "agent_results": [record_agent_result(result)],
            "evidence_refs": list(result.evidence_refs),
            "ai_tokens": result.ai_tokens,
            "degraded": is_degraded,
            "last_node": "reasoning",
        }

    return reasoning_node


def _make_finalize_node(deps: InvestigationWorkflowDeps):
    async def finalize_node(state: WorkflowState) -> dict[str, Any]:
        investigation_id = state.get("investigation_id")
        if investigation_id is None:
            return {"last_node": "finalize", "final_state": "FAILED"}

        degraded = bool(state.get("degraded"))
        target = (
            InvestigationState.REVIEW_REQUIRED
            if degraded
            else InvestigationState.COMPLETED
        )
        try:
            async with deps.database.session() as session:
                await deps.lifecycle_manager.transition(
                    session,
                    investigation_id,
                    target,
                    reason=f"orchestration: finalize ({'degraded' if degraded else 'clean'})",
                )
                await session.commit()
        except Exception as exc:
            log.exception("workflow.finalize_failed")
            return {
                "errors": [
                    record_error(
                        node_name="finalize",
                        agent_name=None,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                ],
                "last_node": "finalize",
                "final_state": "FAILED",
            }

        return {
            "last_node": "finalize",
            "final_state": "REVIEW_REQUIRED" if degraded else "SUCCEEDED",
        }

    return finalize_node


# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------
def _route_after_correlation(state: WorkflowState) -> str:
    if state.get("degraded"):
        # Skip the LLM call when the workflow is already degraded — saves
        # tokens and avoids feeding unstable state to the reasoning agent.
        return "finalize"
    options = state.get("options") or {}
    if options.get("enable_reasoning") is False:
        return "finalize"
    return "reasoning"


# ---------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------
def _build_ctx(
    deps: InvestigationWorkflowDeps,
    state: WorkflowState,
    *,
    agent_run_id: uuid.UUID,
    node_name: str,
    policy,
    inputs_extra: dict[str, Any] | None = None,
) -> AgentExecutionContext:
    investigation_id = state.get("investigation_id")
    memory = (
        InvestigationMemory(
            redis=deps.redis,
            settings=deps.settings,
            investigation_id=investigation_id,
        )
        if investigation_id is not None
        else None
    )
    inputs = dict(state.get("inputs") or {})
    if inputs_extra:
        inputs.update(inputs_extra)
    return AgentExecutionContext(
        agent_run_id=agent_run_id,
        workflow_run_id=state["workflow_run_id"],
        node_name=node_name,
        correlation_id=state.get("correlation_id"),
        investigation_id=investigation_id,
        database=deps.database,
        redis=deps.redis,
        evidence_store=deps.evidence_store,
        event_emitter=deps.event_emitter,
        lifecycle_manager=deps.lifecycle_manager,
        llm=deps.llm,
        memory=memory,
        memory_audit=deps.memory_audit,
        token_budget=deps.token_budget,
        retry_policy=policy,
        circuit_breakers=deps.circuit_breakers,
        inputs=inputs,
        options=dict(state.get("options") or {}),
    )
