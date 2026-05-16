"""Investigation event ORM model — the immutable canonical event log.

PLAN.md §2 schema, §5 `investigation_events` table. Rows are INSERT-only.
The Python attribute ``event_metadata`` maps to the DB column ``metadata``
(we can't name a column ``metadata`` because that conflicts with
``Base.metadata`` in SQLAlchemy's declarative API).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, UUIDMixin
from core.events.types import EventType


class InvestigationEvent(Base, UUIDMixin):
    __tablename__ = "investigation_events"

    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=True,  # system events have no investigation
    )
    event_type: Mapped[EventType] = mapped_column(
        SQLEnum(EventType, name="event_type_enum", native_enum=True),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    target: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evidence_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    __table_args__ = (
        Index("ix_investigation_events_inv_ts", "investigation_id", "timestamp"),
        Index("ix_investigation_events_type", "event_type"),
    )
