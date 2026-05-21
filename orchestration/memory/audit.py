"""MemoryAuditLogger — Postgres audit trail for memory operations.

Every ``append`` / ``recall`` / ``clear`` / ``truncate`` writes one
``memory_audits`` row. We **never** store raw memory content — only a
SHA-256 fingerprint of the entry (or the concatenated summaries on recall)
so an auditor can cross-reference against evidence rows or Redis (within
TTL) but cannot reconstruct the prompt from the audit table alone.
"""
from __future__ import annotations

import enum
import hashlib
import uuid
from typing import Iterable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from storage.postgres.models.memory_audit import MemoryAuditRow

log = structlog.get_logger(__name__)


class MemoryOperation(str, enum.Enum):
    APPEND = "APPEND"
    RECALL = "RECALL"
    CLEAR = "CLEAR"
    TRUNCATE = "TRUNCATE"


def _fingerprint(summaries: Iterable[str]) -> str | None:
    joined = "\n".join(s for s in summaries if s)
    if not joined:
        return None
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class MemoryAuditLogger:
    """Stateless. Takes a session per call to join the caller's tx."""

    async def record(
        self,
        session: AsyncSession,
        *,
        investigation_id: uuid.UUID,
        operation: MemoryOperation,
        actor: str,
        entry_count: int,
        summaries: Iterable[str] = (),
        agent_run_id: uuid.UUID | None = None,
        workflow_run_id: uuid.UUID | None = None,
    ) -> None:
        row = MemoryAuditRow(
            id=uuid.uuid4(),
            investigation_id=investigation_id,
            agent_run_id=agent_run_id,
            workflow_run_id=workflow_run_id,
            operation=operation.value,
            entry_count=entry_count,
            actor=actor,
            content_fingerprint=_fingerprint(summaries),
        )
        session.add(row)
        await session.flush()
        log.debug(
            "memory.audit",
            investigation_id=str(investigation_id),
            operation=operation.value,
            entry_count=entry_count,
            actor=actor,
        )
