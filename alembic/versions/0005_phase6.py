"""Phase 6: production hardening — auth event types + retention scaffolding.

Adds two ``EventType`` enum values used by Phase 6 WP3/WP4:

- ``AUTH_DENIED``            — bearer-token verification failure.
- ``AUTH_PERMISSION_DENIED`` — RBAC denial after a valid token.

Both rows are emitted as fingerprint-only audit records by
``apps/api/exceptions.py`` and the auth dependency. Raw token bodies are
NEVER persisted (CLAUDE.md invariant #12).

Also creates the ``secure_deletion_queue`` table consumed by the WP6
secure-deletion job, and adds the expression index used by the
evidence-retention job to filter on ``provenance->>'level'``.

Revision ID: 0005_phase6
Revises: 0004_orchestration
Create Date: 2026-05-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase6"
down_revision: Union[str, None] = "0004_orchestration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_EVENT_TYPES: tuple[str, ...] = (
    "AUTH_DENIED",
    "AUTH_PERMISSION_DENIED",
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Extend event_type_enum with the Phase 6 auth values.
    for value in NEW_EVENT_TYPES:
        bind.execute(
            sa.text(f"ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS '{value}'")
        )

    # 2) Expression index for the evidence-retention job. Evidence stores
    #    provenance as JSONB; the retention job filters on
    #    (provenance->>'level', created_at). Without this index the
    #    nightly sweep would table-scan as row count grows.
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_evidence_provenance_level_created_at "
            "ON evidence ((provenance->>'level'), created_at)"
        )
    )

    # 3) secure_deletion_queue — written by the firewall when a prompt is
    #    flagged for immediate deletion (leaked API keys, PII bursts).
    #    Consumed every minute by ``core.scheduler.jobs.secure_deletion``.
    op.create_table(
        "secure_deletion_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("target_table", sa.String(length=64), nullable=False),
        sa.Column(
            "target_row_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("processor", sa.String(length=64), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.UniqueConstraint(
            "target_table", "target_row_id", name="uq_secure_deletion_target"
        ),
    )
    op.create_index(
        "ix_secure_deletion_pending",
        "secure_deletion_queue",
        ["enqueued_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_secure_deletion_pending", table_name="secure_deletion_queue")
    op.drop_table("secure_deletion_queue")
    op.get_bind().execute(
        sa.text("DROP INDEX IF EXISTS ix_evidence_provenance_level_created_at")
    )
    # Postgres cannot DROP VALUE from an enum. The two Phase 6 auth event
    # types remain in event_type_enum after downgrade.
