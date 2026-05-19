"""FirewallEvent ORM — immutable audit row for every firewall action.

One row per ``/firewall/decision`` and per ``/firewall/validate-output``
call. The row records *what happened* (decision, classifications,
score), *what was inspected* (prompt SHA-256, optional response SHA-256),
and *what was decided against* (policy_hash). It deliberately stores no
column that could contain raw prompt or response text — CLAUDE.md
invariant #12 is enforced statically by a unit test that inspects
``__table__.columns``.

This table is separate from ``investigation_events`` so the firewall
stream can have its own retention policy without rewriting the event
schema. Every FirewallEvent row links to an Investigation via FK; the
graph correlator hangs the Prompt / Agent nodes off that investigation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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

from core.database.base import Base, UUIDMixin
from firewall.policy.actions import FirewallAction
from firewall.risk.levels import RiskLevel


class FirewallEvent(Base, UUIDMixin):
    __tablename__ = "firewall_events"

    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    target_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    decision: Mapped[FirewallAction] = mapped_column(
        SQLEnum(FirewallAction, name="firewall_action_enum", native_enum=True),
        nullable=False,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SQLEnum(RiskLevel, name="firewall_risk_level_enum", native_enum=True),
        nullable=False,
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)

    classifications: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    rule_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    pattern_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    redaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    evidence_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )

    is_output_validation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="firewall")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_firewall_events_investigation", "investigation_id"),
        Index("ix_firewall_events_decision", "decision"),
        Index("ix_firewall_events_risk_level", "risk_level"),
        Index("ix_firewall_events_created_at", "created_at"),
        Index("ix_firewall_events_prompt_sha256", "prompt_sha256"),
    )
