"""EventEmitter — the only writer to ``investigation_events``.

INSERT-only. The class deliberately exposes no update or delete method;
adding one would be an architectural violation. Every caller must pass a
session so that event emission joins the caller's transaction (so a
state-transition + its event are atomic).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import get_contextvars

from core.events.event import Event
from core.events.types import EventType
from storage.postgres.models.investigation_event import InvestigationEvent

log = structlog.get_logger(__name__)


class EventEmitter:
    """Stateless service. Persists Event domain objects to the events table."""

    async def emit(
        self,
        session: AsyncSession,
        event_type: EventType,
        *,
        source: str,
        investigation_id: uuid.UUID | None = None,
        target: str | None = None,
        evidence_refs: list[uuid.UUID] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence: float = 1.0,
        actor: str = "system",
    ) -> Event:
        correlation_id = get_contextvars().get("correlation_id")
        event = Event(
            event_id=uuid.uuid4(),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            source=source,
            investigation_id=investigation_id,
            correlation_id=correlation_id,
            actor=actor,
            target=target,
            evidence_refs=evidence_refs or [],
            metadata=metadata or {},
            confidence=confidence,
        )
        row = InvestigationEvent(
            id=event.event_id,
            investigation_id=event.investigation_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            source=event.source,
            correlation_id=event.correlation_id,
            actor=event.actor,
            target=event.target,
            evidence_refs=event.evidence_refs,
            event_metadata=event.event_metadata,
            confidence=event.confidence,
        )
        session.add(row)
        await session.flush()
        log.info(
            "event.emitted",
            event_id=str(event.event_id),
            event_type=event.event_type.value,
            investigation_id=str(investigation_id) if investigation_id else None,
        )
        return event
