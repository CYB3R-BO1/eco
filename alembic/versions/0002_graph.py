"""Phase 3: graph audit log + extended event-type enum.

Adds the five new event types from :mod:`core.events.types` (GRAPH_*,
CORRELATION_COMPLETED, INTEGRITY_VIOLATION_DETECTED) and creates the
``graph_rejections`` table that backs the Schema Governance audit trail.

Revision ID: 0002_graph
Revises: 0001_initial
Create Date: 2026-05-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_graph"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_EVENT_TYPES: tuple[str, ...] = (
    "GRAPH_NODE_CREATED",
    "GRAPH_RELATIONSHIP_CREATED",
    "GRAPH_MUTATION_REJECTED",
    "CORRELATION_COMPLETED",
    "INTEGRITY_VIOLATION_DETECTED",
)


def upgrade() -> None:
    # 1) Extend the event_type_enum with the five Phase 3 values.
    #    ALTER TYPE ADD VALUE cannot run inside a transaction block when the
    #    enum is used elsewhere, so we use the per-value form with IF NOT
    #    EXISTS for idempotency.
    bind = op.get_bind()
    for value in NEW_EVENT_TYPES:
        bind.execute(
            sa.text(f"ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS '{value}'")
        )

    # 2) graph_rejections — audit log of every rejected mutation. We capture
    #    enough to reproduce the attempt for a postmortem without storing the
    #    full Cypher (we don't want analysts copy-pasting it back in).
    op.create_table(
        "graph_rejections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("investigations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "attempt_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "actor",
            sa.String(length=128),
            nullable=False,
            server_default="system",
        ),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_graph_rejections_investigation",
        "graph_rejections",
        ["investigation_id"],
    )
    op.create_index(
        "ix_graph_rejections_relationship",
        "graph_rejections",
        ["relationship_type"],
    )
    op.create_index(
        "ix_graph_rejections_created_at",
        "graph_rejections",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_graph_rejections_created_at", table_name="graph_rejections")
    op.drop_index("ix_graph_rejections_relationship", table_name="graph_rejections")
    op.drop_index("ix_graph_rejections_investigation", table_name="graph_rejections")
    op.drop_table("graph_rejections")
    # Postgres does not support DROP VALUE on an enum. The five new event
    # types remain in the enum after downgrade; that's the documented
    # behavior for this kind of migration.
