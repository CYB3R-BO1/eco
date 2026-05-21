"""OrchestrationService — public facade for the orchestration runtime.

Three public methods:

- :meth:`run_workflow` — start a workflow run; returns ``WorkflowRunHandle``.
- :meth:`get_workflow` — fetch run + all agent runs (full audit view).
- :meth:`get_agent_status` — workflow-run summary (status, last node, tokens).

The service owns the workflow-run row lifecycle (PENDING → RUNNING →
SUCCEEDED / REVIEW_REQUIRED / FAILED). Idempotency: callers may pass
``idempotency_key``; if a prior run committed under that key the
service short-circuits with the prior result.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import inputs_fingerprint
from core.events.emitter import EventEmitter
from core.events.types import EventType
from core.database.postgres import Database
from orchestration.runtime.state import new_workflow_state
from orchestration.workflows.registry import WorkflowName
from orchestration.workflows.states import (
    WorkflowRunStatus,
    is_valid_workflow_transition,
)
from storage.postgres.models.agent_run import AgentRunRow
from storage.postgres.models.workflow_run import WorkflowRunRow

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WorkflowRunHandle:
    workflow_run_id: uuid.UUID
    workflow_name: str
    status: WorkflowRunStatus
    investigation_id: uuid.UUID | None
    idempotent_replay: bool = False


class OrchestrationService:
    def __init__(
        self,
        *,
        database: Database,
        event_emitter: EventEmitter,
        graphs: dict[str, Any],  # workflow_name → CompiledStateGraph
    ) -> None:
        self._db = database
        self._events = event_emitter
        self._graphs = graphs

    @property
    def supported_workflows(self) -> list[str]:
        return sorted(self._graphs.keys())

    async def run_workflow(
        self,
        *,
        workflow_name: str,
        inputs: dict[str, Any],
        options: dict[str, Any] | None = None,
        actor: str = "orchestration",
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        background: bool = True,
    ) -> WorkflowRunHandle:
        if workflow_name not in self._graphs:
            raise ValueError(
                f"unknown workflow '{workflow_name}'. "
                f"Supported: {self.supported_workflows}"
            )

        # Idempotency lookup
        if idempotency_key:
            async with self._db.session() as session:
                existing = (
                    await session.execute(
                        select(WorkflowRunRow).where(
                            WorkflowRunRow.idempotency_key == idempotency_key
                        )
                    )
                ).scalar_one_or_none()
            if existing is not None:
                log.info(
                    "orchestration.idempotent_replay",
                    workflow=workflow_name,
                    workflow_run_id=str(existing.id),
                )
                return WorkflowRunHandle(
                    workflow_run_id=existing.id,
                    workflow_name=existing.workflow_name,
                    status=existing.status,
                    investigation_id=existing.investigation_id,
                    idempotent_replay=True,
                )

        # Insert PENDING row.
        workflow_run_id = uuid.uuid4()
        fingerprint = inputs_fingerprint(inputs)
        async with self._db.session() as session:
            row = WorkflowRunRow(
                id=workflow_run_id,
                workflow_name=workflow_name,
                status=WorkflowRunStatus.PENDING,
                investigation_id=None,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                inputs_fingerprint=fingerprint,
                options=options or {},
                actor=actor,
                ai_tokens_input=0,
                ai_tokens_output=0,
                degraded=False,
            )
            session.add(row)
            await session.flush()
            await self._events.emit(
                session,
                EventType.WORKFLOW_RUN_STARTED,
                source="orchestration",
                investigation_id=None,
                target=str(workflow_run_id),
                metadata={
                    "workflow": workflow_name,
                    "inputs_fingerprint": fingerprint,
                    "correlation_id": correlation_id,
                },
                actor=actor,
            )
            await session.commit()

        if background:
            # Fire-and-forget; the API returns 202 and the caller polls
            # /agents/status. Exceptions are logged inside _execute.
            asyncio.create_task(
                self._execute(
                    workflow_run_id=workflow_run_id,
                    workflow_name=workflow_name,
                    inputs=inputs,
                    options=options or {},
                    correlation_id=correlation_id,
                )
            )
        else:
            await self._execute(
                workflow_run_id=workflow_run_id,
                workflow_name=workflow_name,
                inputs=inputs,
                options=options or {},
                correlation_id=correlation_id,
            )

        return WorkflowRunHandle(
            workflow_run_id=workflow_run_id,
            workflow_name=workflow_name,
            status=WorkflowRunStatus.PENDING,
            investigation_id=None,
        )

    async def _execute(
        self,
        *,
        workflow_run_id: uuid.UUID,
        workflow_name: str,
        inputs: dict[str, Any],
        options: dict[str, Any],
        correlation_id: str | None,
    ) -> None:
        graph = self._graphs[workflow_name]
        start_monotonic = time.monotonic()
        await self._transition(workflow_run_id, WorkflowRunStatus.RUNNING)

        state = new_workflow_state(
            workflow_run_id=workflow_run_id,
            workflow_name=workflow_name,
            inputs=inputs,
            options=options,
            correlation_id=correlation_id,
        )
        config = {"configurable": {"thread_id": str(workflow_run_id)}}

        final_state: dict[str, Any] | None = None
        try:
            final_state = await graph.ainvoke(state, config=config)
        except Exception as exc:
            log.exception(
                "orchestration.workflow_failed",
                workflow=workflow_name,
                workflow_run_id=str(workflow_run_id),
            )
            await self._finalize_failed(
                workflow_run_id,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
            )
            return

        await self._finalize_succeeded(
            workflow_run_id=workflow_run_id,
            final_state=final_state or {},
            duration_ms=int((time.monotonic() - start_monotonic) * 1000),
        )

    async def _transition(
        self,
        workflow_run_id: uuid.UUID,
        target: WorkflowRunStatus,
    ) -> None:
        async with self._db.session() as session:
            row = await session.get(WorkflowRunRow, workflow_run_id)
            if row is None:
                return
            if not is_valid_workflow_transition(row.status, target):
                log.warning(
                    "orchestration.invalid_workflow_transition",
                    current=row.status.value,
                    target=target.value,
                    workflow_run_id=str(workflow_run_id),
                )
                return
            row.status = target
            if target is WorkflowRunStatus.RUNNING:
                row.started_at = datetime.now(timezone.utc)
            await session.commit()

    async def _finalize_succeeded(
        self,
        *,
        workflow_run_id: uuid.UUID,
        final_state: dict[str, Any],
        duration_ms: int,
    ) -> None:
        terminal_str = final_state.get("final_state") or "SUCCEEDED"
        if terminal_str == "REVIEW_REQUIRED":
            target = WorkflowRunStatus.REVIEW_REQUIRED
        elif terminal_str == "FAILED":
            target = WorkflowRunStatus.FAILED
        else:
            target = WorkflowRunStatus.SUCCEEDED

        ai_tokens = final_state.get("ai_tokens")
        ai_input = getattr(ai_tokens, "input", 0)
        ai_output = getattr(ai_tokens, "output", 0)
        async with self._db.session() as session:
            row = await session.get(WorkflowRunRow, workflow_run_id)
            if row is None:
                return
            if is_valid_workflow_transition(row.status, target):
                row.status = target
            row.completed_at = datetime.now(timezone.utc)
            row.duration_ms = duration_ms
            row.degraded = bool(final_state.get("degraded"))
            row.ai_tokens_input = int(ai_input)
            row.ai_tokens_output = int(ai_output)
            row.last_node = final_state.get("last_node")
            row.investigation_id = final_state.get("investigation_id")
            event_type = (
                EventType.WORKFLOW_RUN_COMPLETED
                if target is WorkflowRunStatus.SUCCEEDED
                else EventType.WORKFLOW_RUN_DEGRADED
                if target is WorkflowRunStatus.REVIEW_REQUIRED
                else EventType.WORKFLOW_RUN_FAILED
            )
            await self._events.emit(
                session,
                event_type,
                source="orchestration",
                investigation_id=row.investigation_id,
                target=str(workflow_run_id),
                metadata={
                    "status": target.value,
                    "duration_ms": duration_ms,
                    "degraded": row.degraded,
                    "ai_tokens_input": row.ai_tokens_input,
                    "ai_tokens_output": row.ai_tokens_output,
                },
                actor="orchestration",
            )
            await session.commit()

    async def _finalize_failed(
        self,
        workflow_run_id: uuid.UUID,
        *,
        error: str,
        duration_ms: int,
    ) -> None:
        async with self._db.session() as session:
            row = await session.get(WorkflowRunRow, workflow_run_id)
            if row is None:
                return
            if is_valid_workflow_transition(row.status, WorkflowRunStatus.FAILED):
                row.status = WorkflowRunStatus.FAILED
            row.completed_at = datetime.now(timezone.utc)
            row.duration_ms = duration_ms
            row.error = error[:512]
            await self._events.emit(
                session,
                EventType.WORKFLOW_RUN_FAILED,
                source="orchestration",
                investigation_id=row.investigation_id,
                target=str(workflow_run_id),
                metadata={"error": error[:512], "duration_ms": duration_ms},
                actor="orchestration",
            )
            await session.commit()

    # ----------------------------------------------------------
    # Read API
    # ----------------------------------------------------------
    async def get_agent_status(self, workflow_run_id: uuid.UUID) -> dict[str, Any] | None:
        async with self._db.session() as session:
            row = await session.get(WorkflowRunRow, workflow_run_id)
        if row is None:
            return None
        return _row_to_status(row)

    async def get_workflow(self, workflow_run_id: uuid.UUID) -> dict[str, Any] | None:
        async with self._db.session() as session:
            row = await session.get(WorkflowRunRow, workflow_run_id)
            if row is None:
                return None
            agent_rows = (
                await session.execute(
                    select(AgentRunRow)
                    .where(AgentRunRow.workflow_run_id == workflow_run_id)
                    .order_by(AgentRunRow.started_at)
                )
            ).scalars().all()
        return {
            **_row_to_status(row),
            "agent_runs": [_agent_to_dict(r) for r in agent_rows],
        }


def _row_to_status(row: WorkflowRunRow) -> dict[str, Any]:
    return {
        "workflow_run_id": str(row.id),
        "workflow_name": row.workflow_name,
        "status": row.status.value,
        "investigation_id": str(row.investigation_id) if row.investigation_id else None,
        "correlation_id": row.correlation_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "duration_ms": row.duration_ms,
        "degraded": row.degraded,
        "ai_tokens_input": row.ai_tokens_input,
        "ai_tokens_output": row.ai_tokens_output,
        "last_node": row.last_node,
        "error": row.error,
        "actor": row.actor,
    }


def _agent_to_dict(row: AgentRunRow) -> dict[str, Any]:
    return {
        "agent_run_id": str(row.id),
        "agent_name": row.agent_name,
        "node_name": row.node_name,
        "investigation_id": str(row.investigation_id) if row.investigation_id else None,
        "status": row.status.value,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "duration_ms": row.duration_ms,
        "confidence": row.confidence,
        "retries_used": row.retries_used,
        "ai_tokens_input": row.ai_tokens_input,
        "ai_tokens_output": row.ai_tokens_output,
        "evidence_refs": [str(r) for r in (row.evidence_refs or [])],
        "findings_summary": row.findings_summary,
        "error": row.error,
    }
