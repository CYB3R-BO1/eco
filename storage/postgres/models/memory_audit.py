"""MemoryAuditRow ORM — every read/write/clear of investigation memory.

Per ``PLAN.md`` §3 "audit log all memory access". We store only the
fingerprint of the memory entry (SHA-256) — never the raw content. The
fingerprint lets an auditor cross-reference a memory access against the
actual entry in Redis (if still within TTL) or against a downstream
evidence row that quoted it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database.base import Base, UUIDMixin


class MemoryAuditRow(Base, UUIDMixin):
    __tablename__ = "memory_audits"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)

    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_memory_audits_investigation", "investigation_id"),
        Index("ix_memory_audits_operation", "operation"),
        Index("ix_memory_audits_created_at", "created_at"),
    )
