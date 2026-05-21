"""Phase 5: Agent orchestration runtime tables + event-type enum extension.

Adds the thirteen Phase 5 ``EventType`` values, creates the three
orchestration enums (``workflow_run_status_enum``, ``agent_run_status_enum``,
``dlq_queue_enum``), and creates the four orchestration tables
(``workflow_runs``, ``agent_runs``, ``dead_letter_entries``, ``memory_audits``).

The LangGraph checkpointer table (``langgraph_checkpoints``) is owned by
``langgraph-checkpoint-postgres`` and is created idempotently by
``PostgresSaver.setup()`` at API startup — not here.

Privacy invariant (CLAUDE.md #12): none of these tables hold raw prompt,
completion, or memory text — only SHA-256 fingerprints. The static
``test_orchestration_no_raw_text_storage.py`` test enforces this in CI.

Revision ID: 0004_orchestration
Revises: 0003_firewall
Create Date: 2026-05-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_orchestration"
down_revision: Union[str, None] = "0003_firewall"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_EVENT_TYPES: tuple[str, ...] = (
    "WORKFLOW_RUN_STARTED",
    "WORKFLOW_RUN_COMPLETED",
    "WORKFLOW_RUN_FAILED",
    "WORKFLOW_RUN_DEGRADED",
    "AGENT_STARTED",
    "AGENT_COMPLETED",
    "AGENT_FAILED",
    "AGENT_RETRY",
    "MEMORY_ENTRY_APPENDED",
    "MEMORY_ENTRY_TRUNCATED",
    "AI_UNAVAILABLE",
    "REASONING_BLOCKED_BY_FIREWALL",
    "DEAD_LETTER_RECORDED",
)

WORKFLOW_RUN_STATUS_VALUES: tuple[str, ...] = (
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "REVIEW_REQUIRED",
    "FAILED",
)

AGENT_RUN_STATUS_VALUES: tuple[str, ...] = (
    "SUCCESS",
    "DEGRADED",
    "FAILED",
    "TIMEOUT",
    "AI_UNAVAILABLE",
)

DLQ_QUEUE_VALUES: tuple[str, ...] = (
    "ENRICHMENT",
    "GRAPH",
    "REASONING",
    "WORKFLOW",
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Extend event_type_enum with the thirteen Phase 5 values.
    for value in NEW_EVENT_TYPES:
        bind.execute(
            sa.text(f"ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS '{value}'")
        )

    # 2) Create the three orchestration enums idempotently.
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workflow_run_status_enum') THEN
                    CREATE TYPE workflow_run_status_enum AS ENUM (
                        'PENDING', 'RUNNING', 'SUCCEEDED', 'REVIEW_REQUIRED', 'FAILED'
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
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'agent_run_status_enum') THEN
                    CREATE TYPE agent_run_status_enum AS ENUM (
                        'SUCCESS', 'DEGRADED', 'FAILED', 'TIMEOUT', 'AI_UNAVAILABLE'
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
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'dlq_queue_enum') THEN
                    CREATE TYPE dlq_queue_enum AS ENUM (
                        'ENRICHMENT', 'GRAPH', 'REASONING', 'WORKFLOW'
                    );
                END IF;
            END
            $$;
            """
        )
    )

    # 3) workflow_runs — one row per /agents/run invocation.
    op.create_table(
        "workflow_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("workflow_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                *WORKFLOW_RUN_STATUS_VALUES,
                name="workflow_run_status_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("investigations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column(
            "idempotency_key",
            sa.String(length=128),
            nullable=True,
            unique=True,
        ),
        sa.Column("inputs_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "degraded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "ai_tokens_input",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ai_tokens_output",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_node", sa.String(length=64), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column(
            "options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "actor",
            sa.String(length=128),
            nullable=False,
            server_default="orchestration",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_workflow_runs_investigation",
        "workflow_runs",
        ["investigation_id"],
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index(
        "ix_workflow_runs_correlation_id",
        "workflow_runs",
        ["correlation_id"],
    )
    op.create_index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])

    # 4) agent_runs — one row per agent execution inside a workflow.
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("node_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                *AGENT_RUN_STATUS_VALUES,
                name="agent_run_status_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=128),
            nullable=False,
            unique=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "retries_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ai_tokens_input",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ai_tokens_output",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "evidence_refs",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column(
            "findings_summary",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_agent_runs_workflow_run",
        "agent_runs",
        ["workflow_run_id"],
    )
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index(
        "ix_agent_runs_investigation",
        "agent_runs",
        ["investigation_id"],
    )

    # 5) dead_letter_entries — single audit substrate for all four DLQs.
    op.create_table(
        "dead_letter_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "queue_name",
            postgresql.ENUM(
                *DLQ_QUEUE_VALUES,
                name="dlq_queue_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=256), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "retries_attempted",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column(
            "payload_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_actor", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_dlq_queue_name", "dead_letter_entries", ["queue_name"])
    op.create_index(
        "ix_dlq_investigation",
        "dead_letter_entries",
        ["investigation_id"],
    )
    op.create_index(
        "ix_dlq_workflow_run",
        "dead_letter_entries",
        ["workflow_run_id"],
    )
    op.create_index("ix_dlq_created_at", "dead_letter_entries", ["created_at"])

    # 6) memory_audits — audit log for investigation-scoped memory access.
    #    Stores only SHA-256 fingerprints, never raw content.
    op.create_table(
        "memory_audits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "investigation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "workflow_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column(
            "entry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_memory_audits_investigation",
        "memory_audits",
        ["investigation_id"],
    )
    op.create_index("ix_memory_audits_operation", "memory_audits", ["operation"])
    op.create_index("ix_memory_audits_created_at", "memory_audits", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_audits_created_at", table_name="memory_audits")
    op.drop_index("ix_memory_audits_operation", table_name="memory_audits")
    op.drop_index("ix_memory_audits_investigation", table_name="memory_audits")
    op.drop_table("memory_audits")

    op.drop_index("ix_dlq_created_at", table_name="dead_letter_entries")
    op.drop_index("ix_dlq_workflow_run", table_name="dead_letter_entries")
    op.drop_index("ix_dlq_investigation", table_name="dead_letter_entries")
    op.drop_index("ix_dlq_queue_name", table_name="dead_letter_entries")
    op.drop_table("dead_letter_entries")

    op.drop_index("ix_agent_runs_investigation", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_name", table_name="agent_runs")
    op.drop_index("ix_agent_runs_workflow_run", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.drop_index("ix_workflow_runs_created_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_correlation_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_investigation", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    bind = op.get_bind()
    bind.execute(sa.text("DROP TYPE IF EXISTS dlq_queue_enum"))
    bind.execute(sa.text("DROP TYPE IF EXISTS agent_run_status_enum"))
    bind.execute(sa.text("DROP TYPE IF EXISTS workflow_run_status_enum"))
    # Postgres cannot DROP VALUE from an enum. The thirteen Phase 5 event
    # types remain in event_type_enum after downgrade.
