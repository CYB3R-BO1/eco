"""BaseAgent — ABC every concrete agent inherits.

Concrete agents implement :meth:`_run`; :meth:`execute` is the runtime
entrypoint that:

1. Constructs a deterministic ``idempotency_key`` so LangGraph replays
   reuse the existing ``agent_runs`` row.
2. Inserts (or fetches) the ``agent_runs`` row before any side effects.
3. Wraps ``_run`` with a wall-clock timeout (per-agent ``timeout_seconds``).
4. Persists the final :class:`AgentResult` to the row on completion.

Privacy invariant: ``_run`` returns an :class:`AgentResult` carrying
``evidence_refs`` and a small ``findings`` list — never raw text. Callers
that need raw payloads use the evidence store.
"""
from __future__ import annotations

import abc
import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.context import AgentExecutionContext
from agents.result import AgentResult, AgentRunStatus
from core.events.types import EventType
from core.llm.tokens import AITokenUsage
from storage.postgres.models.agent_run import AgentRunRow

log = structlog.get_logger(__name__)


def compute_idempotency_key(
    *,
    agent_name: str,
    workflow_run_id: uuid.UUID,
    node_name: str,
    inputs: dict[str, Any],
) -> str:
    """Deterministic key for ``agent_runs.idempotency_key``.

    LangGraph replays the same node with the same inputs; this key is the
    contract that lets the UNIQUE constraint deduplicate the second
    insert. The inputs dict is canonicalized (sorted keys, default=str)
    before hashing so dict ordering does not break determinism.
    """
    fingerprint = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    raw = f"{agent_name}|{workflow_run_id}|{node_name}|{fingerprint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def inputs_fingerprint(inputs: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class BaseAgent(abc.ABC):
    name: ClassVar[str]
    timeout_seconds: ClassVar[int] = 120
    max_retries: ClassVar[int] = 3

    async def execute(self, ctx: AgentExecutionContext) -> AgentResult:
        idempotency_key = compute_idempotency_key(
            agent_name=self.name,
            workflow_run_id=ctx.workflow_run_id,
            node_name=ctx.node_name,
            inputs=ctx.inputs,
        )
        started_at = datetime.now(timezone.utc)
        start_monotonic = time.monotonic()

        # Replay-safe row insert: if a prior run already wrote a row with
        # this key, return its persisted result instead of re-running.
        existing = await self._fetch_existing(ctx, idempotency_key)
        if existing is not None:
            log.info(
                "agent.replay_short_circuit",
                agent=self.name,
                agent_run_id=str(existing.id),
                idempotency_key=idempotency_key,
            )
            return _result_from_row(existing)

        async with ctx.database.session() as session:
            row = AgentRunRow(
                id=ctx.agent_run_id,
                workflow_run_id=ctx.workflow_run_id,
                agent_name=self.name,
                investigation_id=ctx.investigation_id,
                node_name=ctx.node_name,
                status=AgentRunStatus.SUCCESS,  # placeholder; updated on completion
                idempotency_key=idempotency_key,
                started_at=started_at,
            )
            session.add(row)
            await session.flush()
            await ctx.event_emitter.emit(
                session,
                EventType.AGENT_STARTED,
                source=f"agent:{self.name}",
                investigation_id=ctx.investigation_id,
                target=str(ctx.agent_run_id),
                metadata={
                    "agent": self.name,
                    "node": ctx.node_name,
                    "workflow_run_id": str(ctx.workflow_run_id),
                },
                actor=f"agent:{self.name}",
            )
            await session.commit()

        try:
            result = await asyncio.wait_for(self._run(ctx), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            result = AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.TIMEOUT,
                error=f"agent exceeded timeout_seconds={self.timeout_seconds}",
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
            )
        except Exception as exc:
            log.exception("agent.unhandled_exception", agent=self.name)
            result = AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}"[:512],
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
            )

        # Stamp duration if the agent didn't set it.
        if result.duration_ms == 0:
            result = AgentResult(
                agent_run_id=result.agent_run_id,
                agent_name=result.agent_name,
                status=result.status,
                evidence_refs=result.evidence_refs,
                findings=result.findings,
                confidence=result.confidence,
                error=result.error,
                ai_tokens=result.ai_tokens,
                retries_used=result.retries_used,
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                metadata=result.metadata,
            )

        await self._finalize(ctx, result, started_at)
        return result

    @abc.abstractmethod
    async def _run(self, ctx: AgentExecutionContext) -> AgentResult:
        """Concrete agent body. Must return an :class:`AgentResult`."""

    async def _fetch_existing(
        self, ctx: AgentExecutionContext, idempotency_key: str
    ) -> AgentRunRow | None:
        async with ctx.database.session() as session:
            return (
                await session.execute(
                    select(AgentRunRow).where(
                        AgentRunRow.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one_or_none()

    async def _finalize(
        self,
        ctx: AgentExecutionContext,
        result: AgentResult,
        started_at: datetime,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        async with ctx.database.session() as session:
            row = await session.get(AgentRunRow, ctx.agent_run_id)
            if row is None:
                log.warning(
                    "agent.finalize_row_missing",
                    agent=self.name,
                    agent_run_id=str(ctx.agent_run_id),
                )
                return
            row.status = result.status
            row.completed_at = completed_at
            row.duration_ms = result.duration_ms
            row.confidence = result.confidence
            row.retries_used = result.retries_used
            row.ai_tokens_input = result.ai_tokens.input
            row.ai_tokens_output = result.ai_tokens.output
            row.evidence_refs = list(result.evidence_refs)
            row.findings_summary = {
                "count": len(result.findings),
                "items": result.findings[:50],
            }
            row.error = result.error
            event_type = (
                EventType.AGENT_COMPLETED
                if result.status == AgentRunStatus.SUCCESS
                else EventType.AGENT_FAILED
            )
            await ctx.event_emitter.emit(
                session,
                event_type,
                source=f"agent:{self.name}",
                investigation_id=ctx.investigation_id,
                target=str(ctx.agent_run_id),
                evidence_refs=list(result.evidence_refs),
                metadata={
                    "agent": self.name,
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                    "retries_used": result.retries_used,
                    "ai_tokens_input": result.ai_tokens.input,
                    "ai_tokens_output": result.ai_tokens.output,
                    "error": result.error,
                },
                actor=f"agent:{self.name}",
                confidence=result.confidence,
            )
            await session.commit()


def _result_from_row(row: AgentRunRow) -> AgentResult:
    findings = row.findings_summary.get("items", []) if isinstance(row.findings_summary, dict) else []
    return AgentResult(
        agent_run_id=row.id,
        agent_name=row.agent_name,
        status=row.status,
        evidence_refs=list(row.evidence_refs or []),
        findings=list(findings),
        confidence=row.confidence or 0.0,
        error=row.error,
        ai_tokens=AITokenUsage(
            input=row.ai_tokens_input or 0,
            output=row.ai_tokens_output or 0,
        ),
        retries_used=row.retries_used or 0,
        duration_ms=row.duration_ms or 0,
    )
