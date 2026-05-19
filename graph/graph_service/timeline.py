"""Investigation timeline service.

Reads the immutable ``investigation_events`` table in ascending timestamp
order. The graph is the wrong source for timelines (it's structural, not
chronological); the events table is the deterministic replay log per
CLAUDE.md invariant #1.

The "attack path" reconstruction is a complementary read: starting from
the events in order, follow the corresponding graph edges to render a
chronological narrative. Phase 3 returns the event sequence; the AI
narrative layer is Phase 4.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.postgres.models.investigation_event import InvestigationEvent

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TimelineRecord:
    event_id: uuid.UUID
    event_type: str
    timestamp: datetime
    source: str
    actor: str
    target: str | None
    evidence_refs: list[uuid.UUID]
    confidence: float
    metadata: dict[str, Any]


class TimelineService:
    """Stateless. Pure read-side; doesn't touch Neo4j."""

    async def get(
        self,
        session: AsyncSession,
        investigation_id: uuid.UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[TimelineRecord]:
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        stmt = (
            select(InvestigationEvent)
            .where(InvestigationEvent.investigation_id == investigation_id)
            .order_by(InvestigationEvent.timestamp.asc(), InvestigationEvent.id.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            TimelineRecord(
                event_id=row.id,
                event_type=row.event_type.value,
                timestamp=row.timestamp,
                source=row.source,
                actor=row.actor,
                target=row.target,
                evidence_refs=list(row.evidence_refs or []),
                confidence=row.confidence,
                metadata=dict(row.event_metadata or {}),
            )
            for row in rows
        ]
