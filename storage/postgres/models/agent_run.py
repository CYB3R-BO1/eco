"""AgentRunRow ORM — one row per agent execution inside a workflow.

A workflow has 1..N agent runs (one per LangGraph node that invokes an
agent). The ``idempotency_key`` is deterministic
(sha256(agent_name|workflow_run_id|node_name|inputs_fingerprint)) so a
LangGraph replay reuses the existing row instead of inserting a duplicate.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agents.result import AgentRunStatus
from core.database.base import Base, UUIDMixin


class AgentRunRow(Base, UUIDMixin):
    __tablename__ = "agent_runs"

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        SQLEnum(AgentRunStatus, name="agent_run_status_enum", native_enum=True),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    retries_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    evidence_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, default=list
    )
    findings_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_agent_runs_workflow_run", "workflow_run_id"),
        Index("ix_agent_runs_agent_name", "agent_name"),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_investigation", "investigation_id"),
    )
