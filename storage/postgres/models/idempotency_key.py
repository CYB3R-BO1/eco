"""Idempotency cache for inbound requests.

PLAN.md §11.6. Honoring an ``Idempotency-Key`` header on POST /iocs/ingest
means a retry returns the cached response instead of double-creating an
investigation. TTL cleanup is out of scope for Phase 2 — a scheduled job
in a later phase will prune entries older than ~24h.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
