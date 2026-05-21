"""DeadLetterEntry ORM — one row per permanent failure.

Per ``PLAN.md`` §10.5 there are four logical DLQs (enrichment, graph,
reasoning, workflow). We back them with a single table discriminated by
``queue_name`` — easier to query and audit than four sibling tables, and
matches the "single audit substrate" pattern. The replay tool reads rows
where ``replayed_at IS NULL``; replay is admin-only and never automatic.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database.base import Base, UUIDMixin


class DLQQueue(str, enum.Enum):
    ENRICHMENT = "ENRICHMENT"
    GRAPH = "GRAPH"
    REASONING = "REASONING"
    WORKFLOW = "WORKFLOW"


class DeadLetterEntry(Base, UUIDMixin):
    __tablename__ = "dead_letter_entries"

    queue_name: Mapped[DLQQueue] = mapped_column(
        SQLEnum(DLQQueue, name="dlq_queue_enum", native_enum=True),
        nullable=False,
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    retries_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    payload_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replay_actor: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_dlq_queue_name", "queue_name"),
        Index("ix_dlq_investigation", "investigation_id"),
        Index("ix_dlq_workflow_run", "workflow_run_id"),
        Index("ix_dlq_created_at", "created_at"),
    )
