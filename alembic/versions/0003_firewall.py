"""Phase 4: AI Firewall audit table + extended event-type enum.

Adds the eight Phase 4 EventType values, creates the two firewall enums
(``firewall_action_enum``, ``firewall_risk_level_enum``), and creates the
``firewall_events`` audit table.

Revision ID: 0003_firewall
Revises: 0002_graph
Create Date: 2026-05-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_firewall"
down_revision: Union[str, None] = "0002_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_EVENT_TYPES: tuple[str, ...] = (
    "PROMPT_RECEIVED",
    "PROMPT_ANALYZED",
    "PROMPT_BLOCKED",
    "PROMPT_SANITIZED",
    "PROMPT_REQUIRES_REVIEW",
    "OUTPUT_VALIDATED",
    "OUTPUT_BLOCKED",
    "FIREWALL_RULE_FIRED",
)

FIREWALL_ACTION_VALUES: tuple[str, ...] = (
    "ALLOW",
    "BLOCK",
    "SANITIZE",
    "REQUIRE_REVIEW",
)

FIREWALL_RISK_LEVEL_VALUES: tuple[str, ...] = (
    "SAFE",
    "SUSPICIOUS",
    "HIGH_RISK",
    "MALICIOUS",
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Extend the event_type_enum with the eight Phase 4 values.
    for value in NEW_EVENT_TYPES:
        bind.execute(
            sa.text(f"ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS '{value}'")
        )

    # 2) Create the two firewall enums. CREATE TYPE inside Alembic uses
    #    DO blocks so the migration is idempotent across re-runs.
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'firewall_action_enum') THEN
                    CREATE TYPE firewall_action_enum AS ENUM (
                        'ALLOW', 'BLOCK', 'SANITIZE', 'REQUIRE_REVIEW'
                    );
                END IF;
            END
            $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'firewall_risk_level_enum') THEN
                    CREATE TYPE firewall_risk_level_enum AS ENUM (
                        'SAFE', 'SUSPICIOUS', 'HIGH_RISK', 'MALICIOUS'
                    );
                END IF;
            END
            $$;
            """
        )
    )

    # 3) firewall_events — append-only audit row per decision / validation.
    op.create_table(
        "firewall_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("investigations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("target_provider", sa.String(length=64), nullable=False),
        sa.Column("target_model", sa.String(length=128), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "decision",
            postgresql.ENUM(
                *FIREWALL_ACTION_VALUES,
                name="firewall_action_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "risk_level",
            postgresql.ENUM(
                *FIREWALL_RISK_LEVEL_VALUES,
                name="firewall_risk_level_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column(
            "classifications",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "rule_ids",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "pattern_ids",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "redaction_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "evidence_refs",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column(
            "is_output_validation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "audit_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "actor",
            sa.String(length=128),
            nullable=False,
            server_default="firewall",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_firewall_events_investigation",
        "firewall_events",
        ["investigation_id"],
    )
    op.create_index(
        "ix_firewall_events_decision",
        "firewall_events",
        ["decision"],
    )
    op.create_index(
        "ix_firewall_events_risk_level",
        "firewall_events",
        ["risk_level"],
    )
    op.create_index(
        "ix_firewall_events_created_at",
        "firewall_events",
        ["created_at"],
    )
    op.create_index(
        "ix_firewall_events_prompt_sha256",
        "firewall_events",
        ["prompt_sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_firewall_events_prompt_sha256", table_name="firewall_events")
    op.drop_index("ix_firewall_events_created_at", table_name="firewall_events")
    op.drop_index("ix_firewall_events_risk_level", table_name="firewall_events")
    op.drop_index("ix_firewall_events_decision", table_name="firewall_events")
    op.drop_index("ix_firewall_events_investigation", table_name="firewall_events")
    op.drop_table("firewall_events")

    bind = op.get_bind()
    bind.execute(sa.text("DROP TYPE IF EXISTS firewall_risk_level_enum"))
    bind.execute(sa.text("DROP TYPE IF EXISTS firewall_action_enum"))
    # Postgres does not support DROP VALUE on an enum. The eight new
    # event types remain in event_type_enum after downgrade.
