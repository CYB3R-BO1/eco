"""DeadLetterStore — INSERT-only writer for ``dead_letter_entries``.

Privacy invariant: callers pass a ``payload_metadata`` dict (small,
structured, bounded) and the *fingerprint* of the failed payload — never
raw payload text. The fingerprint lets an operator correlate a DLQ row
with the upstream evidence record that quoted it.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.observability.metrics import DLQ_DEPTH
from storage.postgres.models.dead_letter_entry import DeadLetterEntry, DLQQueue

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DeadLetterWriteResult:
    entry_id: uuid.UUID
    queue_name: DLQQueue


def fingerprint_payload(payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class DeadLetterStore:
    async def record(
        self,
        session: AsyncSession,
        *,
        queue_name: DLQQueue,
        reason: str,
        payload_fingerprint: str,
        retries_attempted: int,
        last_error: str | None = None,
        payload_metadata: dict[str, Any] | None = None,
        workflow_run_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        investigation_id: uuid.UUID | None = None,
    ) -> DeadLetterWriteResult:
        entry_id = uuid.uuid4()
        row = DeadLetterEntry(
            id=entry_id,
            queue_name=queue_name,
            workflow_run_id=workflow_run_id,
            agent_run_id=agent_run_id,
            investigation_id=investigation_id,
            reason=reason[:256],
            payload_fingerprint=payload_fingerprint,
            retries_attempted=retries_attempted,
            last_error=(last_error or "")[:1024] or None,
            payload_metadata=payload_metadata or {},
        )
        session.add(row)
        await session.flush()
        # Live gauge — not the persisted count but a fast-incrementing
        # operational signal that an entry was just written. A scheduled
        # reconciler in WP6 corrects drift against the actual table count.
        DLQ_DEPTH.labels(queue_name=queue_name.value).inc()
        log.warning(
            "dlq.record",
            queue=queue_name.value,
            entry_id=str(entry_id),
            reason=reason,
            retries=retries_attempted,
            workflow_run_id=str(workflow_run_id) if workflow_run_id else None,
        )
        return DeadLetterWriteResult(entry_id=entry_id, queue_name=queue_name)
