"""GraphRejection ORM model — audit log for rejected graph mutations.

Every schema-violation or cardinality-violation rejection from
:class:`graph.governance.SchemaValidator` becomes one row here. Postgres is
the right home (not Neo4j): rejections are exactly the writes that did
*not* happen, so they cannot live in the graph they were rejected from.

This table is also referenced from a parallel ``GRAPH_MUTATION_REJECTED``
event in ``investigation_events`` (carrying ``metadata.rejection_id`` so
the two records cross-link).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, UUIDMixin


class GraphRejection(Base, UUIDMixin):
    __tablename__ = "graph_rejections"

    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(String(), nullable=False)
    attempt_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_graph_rejections_investigation", "investigation_id"),
        Index("ix_graph_rejections_relationship", "relationship_type"),
        Index("ix_graph_rejections_created_at", "created_at"),
    )
