"""DLQ replay — admin-only.

Per PLAN.md "Out of scope": replay is **never** automatic and is **not**
exposed on the public API. This module is intended to be imported by a
CLI shim or a dedicated admin endpoint. It marks the original entry as
``replayed_at = now()`` and records the replay actor.

A real replay needs queue-specific logic (re-enqueue the original
payload), which lives in the agent/workflow layer; this function only
*flags* the DLQ row. Callers wire it together.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.postgres.models.dead_letter_entry import DeadLetterEntry

log = structlog.get_logger(__name__)


class ReplayOutcome(str, enum.Enum):
    MARKED = "MARKED"
    ALREADY_REPLAYED = "ALREADY_REPLAYED"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class ReplayResult:
    entry_id: uuid.UUID
    outcome: ReplayOutcome


async def replay_entry(
    session: AsyncSession,
    *,
    entry_id: uuid.UUID,
    actor: str,
) -> ReplayResult:
    row = (
        await session.execute(
            select(DeadLetterEntry).where(DeadLetterEntry.id == entry_id)
        )
    ).scalar_one_or_none()
    if row is None:
        log.warning("dlq.replay.not_found", entry_id=str(entry_id))
        return ReplayResult(entry_id=entry_id, outcome=ReplayOutcome.NOT_FOUND)
    if row.replayed_at is not None:
        log.info(
            "dlq.replay.already_replayed",
            entry_id=str(entry_id),
            previous_actor=row.replay_actor,
        )
        return ReplayResult(entry_id=entry_id, outcome=ReplayOutcome.ALREADY_REPLAYED)
    row.replayed_at = datetime.now(timezone.utc)
    row.replay_actor = actor
    await session.flush()
    log.info("dlq.replay.marked", entry_id=str(entry_id), actor=actor)
    return ReplayResult(entry_id=entry_id, outcome=ReplayOutcome.MARKED)
