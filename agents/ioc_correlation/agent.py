"""IOCCorrelationAgent.

Wraps :class:`graph.correlation.correlator.GraphCorrelator` — the
deterministic Phase 3 correlator that materializes investigation evidence
as Neo4j nodes/edges via :class:`GraphService` (the only writer).

The agent does **not** open a session for the correlator (the correlator
manages that itself). It surfaces the correlator's stats as findings and
runs the integrity gate to determine confidence.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from agents.base import BaseAgent
from agents.context import AgentExecutionContext
from agents.result import AgentResult, AgentRunStatus
from graph.correlation.correlator import GraphCorrelator
from graph.graph_service.service import GraphService

log = structlog.get_logger(__name__)


class IOCCorrelationAgent(BaseAgent):
    name = "ioc_correlation"
    timeout_seconds = 180
    max_retries = 0

    def __init__(
        self,
        *,
        correlator: GraphCorrelator,
        graph_service: GraphService,
    ) -> None:
        self._correlator = correlator
        self._graph = graph_service

    async def _run(self, ctx: AgentExecutionContext) -> AgentResult:
        if ctx.investigation_id is None:
            return AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.FAILED,
                error="IOCCorrelationAgent requires an investigation_id",
            )

        started = time.monotonic()
        stats = await self._correlator.correlate(ctx.investigation_id)
        report = await self._graph.integrity.check(ctx.investigation_id)

        findings: list[dict[str, Any]] = [
            {
                "stats": {
                    "nodes_created": stats.nodes_created,
                    "edges_created": stats.edges_created,
                    "edges_rejected": stats.edges_rejected,
                    "evidence_processed": stats.evidence_processed,
                    "entities_processed": stats.entities_processed,
                },
                "integrity_violations": report.has_violations,
            }
        ]

        if report.has_violations:
            status = AgentRunStatus.DEGRADED
            confidence = 0.4
        elif stats.edges_rejected > 0:
            status = AgentRunStatus.DEGRADED
            confidence = 0.7
        else:
            status = AgentRunStatus.SUCCESS
            confidence = 0.95

        if ctx.memory is not None:
            try:
                from orchestration.memory.entry import MemoryEntry

                entry = MemoryEntry.new(
                    investigation_id=ctx.investigation_id,
                    agent_name=self.name,
                    summary=(
                        f"correlation: nodes={stats.nodes_created} "
                        f"edges={stats.edges_created} rejected={stats.edges_rejected} "
                        f"integrity_violations={report.has_violations}"
                    ),
                    payload={
                        "edges_rejected": stats.edges_rejected,
                        "violations": report.has_violations,
                    },
                )
                await ctx.memory.append(entry)
            except Exception:
                log.exception("agent.ioc_correlation.memory_append_failed")

        return AgentResult(
            agent_run_id=ctx.agent_run_id,
            agent_name=self.name,
            status=status,
            evidence_refs=[],
            findings=findings,
            confidence=confidence,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"integrity": "violations" if report.has_violations else "clean"},
        )
