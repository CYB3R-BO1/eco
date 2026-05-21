"""Firewall workflow.

LangGraph DAG (PLAN.md §7, condensed):

::

    START → firewall_decide → (branch on decision)
              ↘ REQUIRE_REVIEW → reasoning → finalize → END
              ↘ ALLOW/SANITIZE/BLOCK    → finalize → END

The ``firewall_decide`` node wraps :meth:`FirewallService.decide` as a
single opaque LangGraph node (per the wrap-don't-decompose user decision
in plan mode). It already creates the per-prompt Investigation and
drives the lifecycle FSM internally; the orchestration layer only adds
the workflow-run row, optional reasoning explanation on REQUIRE_REVIEW,
and the audit trail.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from agents.context import AgentExecutionContext
from agents.reasoning.agent import ReasoningAgent
from agents.result import AgentRunStatus
from core.cache.redis import RedisClient
from core.config.settings import OrchestrationSettings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.llm.budget import InvestigationTokenBudget
from core.llm.client import LLMClient
from evidence.store import EvidenceStore
from firewall.models.prompt import ModelTarget, PromptInput, WorkflowContext
from firewall.policy.actions import FirewallAction
from firewall.service import FirewallService, serialize_outcome
from investigation.lifecycle.manager import LifecycleManager
from orchestration.memory.audit import MemoryAuditLogger
from orchestration.memory.store import InvestigationMemory
from orchestration.retry.circuit_breaker import CircuitBreakerRegistry
from orchestration.retry.policies import DEFAULT_AI_POLICY
from orchestration.runtime.state import (
    WorkflowState,
    record_agent_result,
    record_error,
)

log = structlog.get_logger(__name__)


@dataclass
class FirewallWorkflowDeps:
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
    firewall_service: FirewallService
    reasoning_agent: ReasoningAgent


def build_firewall_graph(deps: FirewallWorkflowDeps, *, checkpointer):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkflowState)
    graph.add_node("firewall_decide", _make_firewall_decide_node(deps))
    graph.add_node("reasoning", _make_firewall_reasoning_node(deps))
    graph.add_node("finalize", _make_finalize_node(deps))

    graph.add_edge(START, "firewall_decide")
    graph.add_conditional_edges(
        "firewall_decide",
        _route_after_firewall,
        {"reasoning": "reasoning", "finalize": "finalize"},
    )
    graph.add_edge("reasoning", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


def _make_firewall_decide_node(deps: FirewallWorkflowDeps):
    async def node(state: WorkflowState) -> dict[str, Any]:
        inputs = state.get("inputs") or {}
        prompt = inputs.get("prompt")
        target_data = inputs.get("target_model") or {}
        if not isinstance(prompt, str) or not prompt:
            return {
                "errors": [
                    record_error(
                        node_name="firewall_decide",
                        agent_name=None,
                        reason="missing 'prompt' string in inputs",
                    )
                ],
                "degraded": True,
                "final_state": "FAILED",
                "last_node": "firewall_decide",
            }

        workflow_ctx = None
        wf_id_raw = inputs.get("workflow_id")
        if wf_id_raw:
            try:
                workflow_ctx = WorkflowContext(
                    workflow_id=uuid.UUID(str(wf_id_raw)),
                    route=inputs.get("route"),
                )
            except (TypeError, ValueError):
                pass

        prompt_input = PromptInput(
            prompt=prompt,
            target_model=ModelTarget(
                provider=str(target_data.get("provider", "openai")),
                model=str(target_data.get("model", "gpt-4o-mini")),
            ),
            workflow_context=workflow_ctx,
        )

        try:
            outcome = await deps.firewall_service.decide(
                prompt_input,
                idempotency_key=inputs.get("idempotency_key"),
                correlation_id=state.get("correlation_id"),
            )
        except Exception as exc:
            log.exception("workflow.firewall_decide_failed")
            return {
                "errors": [
                    record_error(
                        node_name="firewall_decide",
                        agent_name=None,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                ],
                "degraded": True,
                "final_state": "FAILED",
                "last_node": "firewall_decide",
            }

        serialized = serialize_outcome(outcome)
        return {
            "investigation_id": outcome.investigation_id,
            "firewall_decision": serialized,
            "findings": [
                {
                    "decision": serialized["decision"],
                    "risk_score": serialized["risk_score"],
                    "risk_level": serialized["risk_level"],
                    "prompt_sha256": serialized["prompt_fingerprint"],
                }
            ],
            "last_node": "firewall_decide",
            "degraded": outcome.decision.action is FirewallAction.REQUIRE_REVIEW,
        }

    return node


def _route_after_firewall(state: WorkflowState) -> str:
    decision = state.get("firewall_decision") or {}
    action = decision.get("decision")
    options = state.get("options") or {}
    if action == FirewallAction.REQUIRE_REVIEW.value and options.get("enable_reasoning") is not False:
        return "reasoning"
    return "finalize"


def _make_firewall_reasoning_node(deps: FirewallWorkflowDeps):
    async def node(state: WorkflowState) -> dict[str, Any]:
        investigation_id = state.get("investigation_id")
        if investigation_id is None:
            return {"last_node": "reasoning"}

        memory = InvestigationMemory(
            redis=deps.redis,
            settings=deps.settings,
            investigation_id=investigation_id,
        )
        ctx = AgentExecutionContext(
            agent_run_id=uuid.uuid4(),
            workflow_run_id=state["workflow_run_id"],
            node_name="reasoning",
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
            retry_policy=DEFAULT_AI_POLICY,
            circuit_breakers=deps.circuit_breakers,
            inputs={"findings": state.get("findings") or []},
            options=dict(state.get("options") or {}),
        )
        result = await deps.reasoning_agent.execute(ctx)
        is_degraded = result.status != AgentRunStatus.SUCCESS
        return {
            "reasoning_result": {
                "status": result.status.value,
                "duration_ms": result.duration_ms,
            },
            "agent_results": [record_agent_result(result)],
            "evidence_refs": list(result.evidence_refs),
            "ai_tokens": result.ai_tokens,
            "degraded": is_degraded,
            "last_node": "reasoning",
        }

    return node


def _make_finalize_node(deps: FirewallWorkflowDeps):
    async def node(state: WorkflowState) -> dict[str, Any]:
        # FirewallService.decide already drove the investigation FSM to its
        # terminal state inside ``_persist_decision`` — we only set the
        # workflow-run terminal here.
        if state.get("final_state") == "FAILED":
            return {"last_node": "finalize"}
        decision = state.get("firewall_decision") or {}
        action = decision.get("decision")
        if action == FirewallAction.REQUIRE_REVIEW.value or state.get("degraded"):
            final = "REVIEW_REQUIRED"
        else:
            final = "SUCCEEDED"
        return {"last_node": "finalize", "final_state": final}

    return node
