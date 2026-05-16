"""Enrichment audit table.

Caches the full request/response of every enrichment call for forensic
replay. Redis is the *hot* cache that gates re-fetches; this table is the
durable audit record.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, UUIDMixin


class EnrichmentResultRow(Base, UUIDMixin):
    __tablename__ = "enrichment_results"

    ioc_evidence_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_enrichment_results_fingerprint", "request_fingerprint"),
        Index("ix_enrichment_results_ioc", "ioc_evidence_id"),
    )
