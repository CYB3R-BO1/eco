"""FirewallGraphCorrelator.

Maps a recorded :class:`firewall.models.reports.Decision` to graph state:

* :class:`graph.governance.node_types.NodeType.PROMPT` for the prompt
  itself (id = a deterministic UUID derived from the prompt fingerprint,
  so replays produce the same node).
* :class:`NodeType.AGENT` for the target LLM (id = UUID5 over
  ``provider:model`` so the agent node is stable across prompts).
* :class:`NodeType.WORKFLOW` (optional) for the caller workflow id.
* :class:`NodeType.FINDING` for every rule that fired with weight ≥ the
  policy's finding_weight_floor.

Then materializes the relationship edges that the Phase 3 matrix already
accepts: ``Prompt → Investigation`` (PART_OF), ``Prompt → Agent``
(ANALYZED_BY), ``Prompt → Agent`` (BLOCKED, only on BLOCK), ``Prompt →
Workflow`` (TRIGGERED), ``Agent → Finding`` (GENERATED).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.events.emitter import EventEmitter
from core.events.types import EventType
from firewall.models.prompt import PromptInput
from firewall.models.reports import Decision
from firewall.policy.actions import FirewallAction
from firewall.policy.policy import FirewallPolicy
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType
from graph.graph_service.service import GraphService

log = structlog.get_logger(__name__)

# UUID5 namespaces — fixed so the same prompt fingerprint / agent ident
# always yield the same node id. Generated once and never changed.
_PROMPT_NAMESPACE = uuid.UUID("8b4f1f6c-3c01-4a44-8d23-7c2f6a1d4e10")
_AGENT_NAMESPACE = uuid.UUID("2a9c6a3e-1b1d-46a7-9d6e-5d3a08c1f2b9")


@dataclass(frozen=True)
class FirewallCorrelationStats:
    prompt_node_new: bool
    agent_node_new: bool
    workflow_node_new: bool
    findings_created: int
    edges_created: int
    edges_rejected: int


class FirewallGraphCorrelator:
    """Materialize a Decision into Neo4j.

    The correlator only *reads* the Decision — it never modifies it.
    Audit data (which firewall_event the nodes belong to) is passed as
    edge metadata so the graph slice carries the join key back to
    Postgres.
    """

    def __init__(
        self,
        *,
        graph_service: GraphService,
        event_emitter: EventEmitter,
        policy: FirewallPolicy,
    ) -> None:
        self._graph = graph_service
        self._events = event_emitter
        self._policy = policy

    async def correlate(
        self,
        pg_session: AsyncSession,
        *,
        investigation_id: uuid.UUID,
        firewall_event_id: uuid.UUID,
        prompt_input: PromptInput,
        decision: Decision,
    ) -> FirewallCorrelationStats:
        stats_nodes = {"prompt": False, "agent": False, "workflow": False}
        edges_created = 0
        edges_rejected = 0
        findings_created = 0

        # --- Investigation node (Phase 3 invariant: every subgraph anchors here) -
        await self._graph.mutator.upsert_node(
            pg_session,
            NodeType.INVESTIGATION,
            investigation_id,
            {
                "title": f"firewall:{decision.action.value}",
                "status": "ACTIVE",
                "severity": _severity_for(decision.action),
                "confidence": float(decision.analysis.risk_score or 0.0),
            },
            investigation_id=investigation_id,
        )

        # --- Prompt node --------------------------------------------------
        prompt_node_id = _prompt_node_id(decision.analysis.prompt_fingerprint)
        prompt_props = {
            "fingerprint": decision.analysis.prompt_fingerprint,
            "length_bytes": decision.analysis.prompt_length,
            "decision": decision.action.value,
            "risk_score": decision.analysis.risk_score,
            "risk_level": decision.analysis.risk_level.value,
            "classifications": [c.value for c in decision.analysis.classifications],
            "confidence": decision.analysis.risk_score,
        }
        prompt_result = await self._graph.mutator.upsert_node(
            pg_session,
            NodeType.PROMPT,
            prompt_node_id,
            prompt_props,
            investigation_id=investigation_id,
        )
        stats_nodes["prompt"] = prompt_result.was_new

        # --- Agent node ---------------------------------------------------
        agent_ident = prompt_input.target_model.identifier()
        agent_node_id = _agent_node_id(agent_ident)
        agent_result = await self._graph.mutator.upsert_node(
            pg_session,
            NodeType.AGENT,
            agent_node_id,
            {
                "provider": prompt_input.target_model.provider,
                "model": prompt_input.target_model.model,
                "identifier": agent_ident,
                "confidence": 1.0,
            },
            investigation_id=investigation_id,
        )
        stats_nodes["agent"] = agent_result.was_new

        # --- Optional Workflow node --------------------------------------
        workflow_node_id: uuid.UUID | None = None
        if prompt_input.workflow_context is not None:
            workflow_node_id = prompt_input.workflow_context.workflow_id
            wf_result = await self._graph.mutator.upsert_node(
                pg_session,
                NodeType.WORKFLOW,
                workflow_node_id,
                {
                    "route": prompt_input.workflow_context.route or "",
                    "confidence": 1.0,
                },
                investigation_id=investigation_id,
            )
            stats_nodes["workflow"] = wf_result.was_new

        # --- Edges -------------------------------------------------------
        # Prompt -[:PART_OF]-> Investigation
        edge_metadata = {
            "firewall_event_id": str(firewall_event_id),
            "decision": decision.action.value,
        }
        e1 = await self._graph.mutator.create_relationship(
            pg_session,
            NodeType.PROMPT,
            prompt_node_id,
            RelationshipType.PART_OF,
            NodeType.INVESTIGATION,
            investigation_id,
            confidence=1.0,
            investigation_id=investigation_id,
            metadata=edge_metadata,
        )
        edges_created, edges_rejected = _tally(e1, edges_created, edges_rejected)

        # Prompt -[:ANALYZED_BY]-> Agent
        e2 = await self._graph.mutator.create_relationship(
            pg_session,
            NodeType.PROMPT,
            prompt_node_id,
            RelationshipType.ANALYZED_BY,
            NodeType.AGENT,
            agent_node_id,
            confidence=decision.analysis.risk_score or 0.0,
            investigation_id=investigation_id,
            metadata={**edge_metadata, "score": decision.analysis.risk_score},
        )
        edges_created, edges_rejected = _tally(e2, edges_created, edges_rejected)

        # Prompt -[:BLOCKED]-> Agent (only on BLOCK)
        if decision.action is FirewallAction.BLOCK:
            e3 = await self._graph.mutator.create_relationship(
                pg_session,
                NodeType.PROMPT,
                prompt_node_id,
                RelationshipType.BLOCKED,
                NodeType.AGENT,
                agent_node_id,
                confidence=decision.analysis.risk_score or 1.0,
                investigation_id=investigation_id,
                metadata={
                    **edge_metadata,
                    "rule_ids": list(decision.explainability.matched_rules),
                    "score": decision.analysis.risk_score,
                },
            )
            edges_created, edges_rejected = _tally(e3, edges_created, edges_rejected)

        # Prompt -[:TRIGGERED]-> Workflow (optional)
        if workflow_node_id is not None:
            e4 = await self._graph.mutator.create_relationship(
                pg_session,
                NodeType.PROMPT,
                prompt_node_id,
                RelationshipType.TRIGGERED,
                NodeType.WORKFLOW,
                workflow_node_id,
                confidence=1.0,
                investigation_id=investigation_id,
                metadata=edge_metadata,
            )
            edges_created, edges_rejected = _tally(e4, edges_created, edges_rejected)

        # --- Finding nodes (one per fired rule above weight floor) -------
        for signal in decision.analysis.signals:
            if signal.rule_id is None:
                continue
            if signal.weight < self._policy.finding_weight_floor:
                continue
            finding_id = _finding_node_id(
                decision.analysis.prompt_fingerprint, signal.rule_id
            )
            f_result = await self._graph.mutator.upsert_node(
                pg_session,
                NodeType.FINDING,
                finding_id,
                {
                    "rule_id": signal.rule_id,
                    "category": signal.category.value,
                    "severity": signal.severity,
                    "confidence": signal.severity,
                    "explanation": signal.explanation,
                },
                investigation_id=investigation_id,
            )
            if f_result.was_new:
                findings_created += 1
            # Agent -[:GENERATED]-> Finding
            ef = await self._graph.mutator.create_relationship(
                pg_session,
                NodeType.AGENT,
                agent_node_id,
                RelationshipType.GENERATED,
                NodeType.FINDING,
                finding_id,
                confidence=signal.severity,
                investigation_id=investigation_id,
                metadata={**edge_metadata, "rule_id": signal.rule_id},
            )
            edges_created, edges_rejected = _tally(ef, edges_created, edges_rejected)

        await self._events.emit(
            pg_session,
            EventType.CORRELATION_COMPLETED,
            source="firewall_correlator",
            investigation_id=investigation_id,
            target=str(firewall_event_id),
            metadata={
                "firewall_event_id": str(firewall_event_id),
                "nodes": stats_nodes,
                "findings_created": findings_created,
                "edges_created": edges_created,
                "edges_rejected": edges_rejected,
            },
        )

        stats = FirewallCorrelationStats(
            prompt_node_new=stats_nodes["prompt"],
            agent_node_new=stats_nodes["agent"],
            workflow_node_new=stats_nodes["workflow"],
            findings_created=findings_created,
            edges_created=edges_created,
            edges_rejected=edges_rejected,
        )
        log.info(
            "firewall.graph.correlated",
            investigation_id=str(investigation_id),
            firewall_event_id=str(firewall_event_id),
            **stats.__dict__,
        )
        return stats


def _prompt_node_id(fingerprint: str) -> uuid.UUID:
    return uuid.uuid5(_PROMPT_NAMESPACE, fingerprint)


def _agent_node_id(identifier: str) -> uuid.UUID:
    return uuid.uuid5(_AGENT_NAMESPACE, identifier)


def _finding_node_id(prompt_fingerprint: str, rule_id: str) -> uuid.UUID:
    return uuid.uuid5(_PROMPT_NAMESPACE, f"finding:{prompt_fingerprint}:{rule_id}")


def _tally(result, created: int, rejected: int) -> tuple[int, int]:
    if result is None:
        return created, rejected + 1
    if result.was_new:
        return created + 1, rejected
    return created, rejected


def _severity_for(action: FirewallAction) -> str:
    return {
        FirewallAction.ALLOW: "low",
        FirewallAction.SANITIZE: "medium",
        FirewallAction.REQUIRE_REVIEW: "medium",
        FirewallAction.BLOCK: "high",
    }[action]
