"""EnrichmentAgent.

Wraps :class:`investigation.enrichment.executor.EnrichmentExecutor`. The
agent operates on the *already-extracted* IOCs of an investigation: it
re-loads them from Postgres (so the agent body is deterministic given
``investigation_id``) and asks the executor to enrich each one.

The executor already implements per-provider retry + circuit breaker +
Redis cache. This agent layer adds:

- A unified :class:`AgentResult` shape (status, confidence, evidence_refs).
- Degraded handling: if any IOC's enrichment lands in the executor's
  internal failure path, the agent returns ``DEGRADED`` rather than
  ``SUCCESS`` so the workflow can route to ``REVIEW_REQUIRED`` per
  PLAN.md §10.5.
- DLQ writes are deferred to the workflow runtime; the agent only
  surfaces the failure state.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from agents.base import BaseAgent
from agents.context import AgentExecutionContext
from agents.result import AgentResult, AgentRunStatus
from investigation.enrichment.executor import EnrichmentExecutor
from resolution.service import EntityResolutionService, ResolvedEntity
from resolution.types import EntityType
from storage.postgres.models.evidence import EvidenceRow

log = structlog.get_logger(__name__)


class EnrichmentAgent(BaseAgent):
    name = "enrichment"
    timeout_seconds = 300
    max_retries = 0  # the executor owns retries internally

    def __init__(
        self,
        *,
        executor: EnrichmentExecutor,
        resolver: EntityResolutionService,
    ) -> None:
        self._executor = executor
        self._resolver = resolver

    async def _run(self, ctx: AgentExecutionContext) -> AgentResult:
        if ctx.investigation_id is None:
            return AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.FAILED,
                error="EnrichmentAgent requires an investigation_id",
            )

        started = time.monotonic()
        head_evidence_id, resolved = await self._load_iocs(ctx)
        if not resolved:
            return AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.SUCCESS,
                evidence_refs=[],
                findings=[],
                confidence=1.0,
                duration_ms=int((time.monotonic() - started) * 1000),
                metadata={"reason": "no IOCs found for enrichment"},
            )

        provider_failures = 0
        findings: list[dict[str, Any]] = []
        evidence_refs: list[uuid.UUID] = []

        for resolved_entity, ioc_evidence_id in resolved:
            try:
                results = await self._executor.enrich(
                    resolved_entity,
                    investigation_id=ctx.investigation_id,
                    ioc_evidence_id=ioc_evidence_id,
                    chain_of_custody=[head_evidence_id, ioc_evidence_id]
                    if head_evidence_id
                    else [ioc_evidence_id],
                )
            except Exception as exc:
                log.exception(
                    "agent.enrichment.executor_failed",
                    entity_id=str(resolved_entity.entity_id),
                )
                provider_failures += 1
                findings.append(
                    {
                        "entity_id": str(resolved_entity.entity_id),
                        "entity_type": resolved_entity.entity_type.value,
                        "error": f"{type(exc).__name__}: {exc}"[:256],
                    }
                )
                continue

            ok = sum(1 for r in results if r.success)
            failures = sum(1 for r in results if not r.success)
            provider_failures += failures
            findings.append(
                {
                    "entity_id": str(resolved_entity.entity_id),
                    "entity_type": resolved_entity.entity_type.value,
                    "providers_ok": ok,
                    "providers_failed": failures,
                }
            )

        confidence = 1.0 if provider_failures == 0 else 0.6
        status = (
            AgentRunStatus.SUCCESS
            if provider_failures == 0
            else AgentRunStatus.DEGRADED
        )

        # Append to investigation memory so downstream agents can recall.
        if ctx.memory is not None and findings:
            try:
                from orchestration.memory.entry import MemoryEntry

                entry = MemoryEntry.new(
                    investigation_id=ctx.investigation_id,
                    agent_name=self.name,
                    summary=(
                        f"enriched {len(findings)} IOCs; "
                        f"provider_failures={provider_failures}"
                    ),
                    payload={"finding_count": len(findings)},
                )
                await ctx.memory.append(entry)
            except Exception:
                log.exception("agent.enrichment.memory_append_failed")

        return AgentResult(
            agent_run_id=ctx.agent_run_id,
            agent_name=self.name,
            status=status,
            evidence_refs=evidence_refs,
            findings=findings,
            confidence=confidence,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={
                "iocs_processed": len(resolved),
                "provider_failures": provider_failures,
            },
        )

    async def _load_iocs(
        self, ctx: AgentExecutionContext
    ) -> tuple[uuid.UUID | None, list[tuple[ResolvedEntity, uuid.UUID]]]:
        async with ctx.database.session() as session:
            rows = (
                await session.execute(
                    select(EvidenceRow).where(
                        EvidenceRow.investigation_id == ctx.investigation_id
                    )
                )
            ).scalars().all()

            head_evidence_id: uuid.UUID | None = None
            resolved: list[tuple[ResolvedEntity, uuid.UUID]] = []

            for row in rows:
                if row.source == "user_supplied" or row.type == "raw_log":
                    head_evidence_id = row.id
                    continue
                # Only re-resolve IOC-typed evidence rows produced by extraction.
                if row.source != "internal_extraction":
                    continue
                raw = row.raw_data or {}
                value = raw.get("value")
                if not value:
                    continue
                # Map evidence.type back to EntityType. Evidence.type holds
                # ``EntityType.value`` (set in pipeline._process).
                try:
                    entity_type = EntityType(row.type)
                except ValueError:
                    continue
                resolved_entity = await self._resolver.resolve(
                    session, value, entity_type
                )
                resolved.append((resolved_entity, row.id))

        return head_evidence_id, resolved
