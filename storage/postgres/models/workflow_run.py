"""WorkflowRunRow ORM — one row per ``/agents/run`` invocation.

This is the durable record of an orchestration run. The LangGraph
checkpointer's table (``langgraph_checkpoints``) stores mid-execution
state for replay; this row is the *summary* an auditor would scan to
answer "what did the platform do for request X?".

Privacy invariant: no column stores raw input text. The original
request body is fingerprinted via ``inputs_fingerprint`` (SHA-256) and
the caller's domain rows (Investigation, FirewallEvent) hold the
domain-specific summaries.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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
from orchestration.workflows.states import WorkflowRunStatus


class WorkflowRunRow(Base, UUIDMixin):
    __tablename__ = "workflow_runs"

    workflow_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLEnum(WorkflowRunStatus, name="workflow_run_status_enum", native_enum=True),
        nullable=False,
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    inputs_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="orchestration")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_workflow_runs_investigation", "investigation_id"),
        Index("ix_workflow_runs_status", "status"),
        Index("ix_workflow_runs_correlation_id", "correlation_id"),
        Index("ix_workflow_runs_created_at", "created_at"),
    )
