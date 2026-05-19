"""Persistence + audit emission for rejected graph mutations.

Rejections are both a Postgres row (``graph_rejections``) and an
``investigation_events`` event (``GRAPH_MUTATION_REJECTED``). The two are
cross-linked via ``metadata.rejection_id`` on the event so an auditor can
walk from either side.

Why both? The events table is the chronological replay log (CLAUDE.md
invariant #1); the rejections table is the structured query surface (filter
by relationship_type, by investigation, count rejections per provider).
Different access patterns, same source of truth.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import get_contextvars

from core.events.emitter import EventEmitter
from core.events.types import EventType
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType
from storage.postgres.models.graph_rejection import GraphRejection

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RejectedMutation:
    source_type: NodeType
    relationship_type: RelationshipType
    target_type: NodeType
    reason: str
    source_id: uuid.UUID | None = None
    target_id: uuid.UUID | None = None
    investigation_id: uuid.UUID | None = None
    attempt_metadata: dict[str, Any] | None = None


class RejectionStore:
    """Records a rejected mutation in Postgres + emits the audit event.

    Both writes share the caller's session so the rejection record and its
    audit event commit atomically.
    """

    def __init__(self, event_emitter: EventEmitter) -> None:
        self._events = event_emitter

    async def record(
        self,
        session: AsyncSession,
        rejection: RejectedMutation,
    ) -> uuid.UUID:
        rejection_id = uuid.uuid4()
        correlation_id = get_contextvars().get("correlation_id")

        row = GraphRejection(
            id=rejection_id,
            investigation_id=rejection.investigation_id,
            source_type=rejection.source_type.value,
            source_id=rejection.source_id,
            relationship_type=rejection.relationship_type.value,
            target_type=rejection.target_type.value,
            target_id=rejection.target_id,
            reason=rejection.reason,
            attempt_metadata=rejection.attempt_metadata or {},
            actor="system",
            correlation_id=correlation_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)

        await self._events.emit(
            session,
            EventType.GRAPH_MUTATION_REJECTED,
            source="graph_governance",
            investigation_id=rejection.investigation_id,
            target=(
                f"({rejection.source_type.value})-"
                f"[{rejection.relationship_type.value}]->"
                f"({rejection.target_type.value})"
            ),
            metadata={
                "rejection_id": str(rejection_id),
                "source_type": rejection.source_type.value,
                "source_id": str(rejection.source_id) if rejection.source_id else None,
                "relationship_type": rejection.relationship_type.value,
                "target_type": rejection.target_type.value,
                "target_id": str(rejection.target_id) if rejection.target_id else None,
                "reason": rejection.reason,
            },
            confidence=0.0,
        )

        log.warning(
            "graph.mutation.rejected",
            rejection_id=str(rejection_id),
            investigation_id=(
                str(rejection.investigation_id) if rejection.investigation_id else None
            ),
            source=rejection.source_type.value,
            rel=rejection.relationship_type.value,
            target=rejection.target_type.value,
            reason=rejection.reason,
        )
        return rejection_id
