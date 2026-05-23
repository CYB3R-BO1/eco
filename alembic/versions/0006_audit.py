"""Phase 7: production audit indexes.

Adds three composite indexes the audit pass identified as production
hot paths missing coverage:

- ``ix_investigations_status_created_at`` — supports both the
  status-filtered list queries and the workflow-retention sweep
  (``status='COMPLETED' AND created_at < cutoff``).
- ``ix_evidence_investigation_created_at`` — supports the
  ``GET /investigations/{id}`` evidence enumeration which already
  sorts by ``created_at``.
- ``ix_idempotency_keys_created_at`` — supports the new
  ``retention_idempotency`` job's cutoff query.

All three use ``IF NOT EXISTS`` so the migration is safe to re-run
against partially-applied environments.

Revision ID: 0006_audit
Revises: 0005_phase6
Create Date: 2026-05-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_audit"
down_revision: Union[str, None] = "0005_phase6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_investigations_status_created_at "
            "ON investigations (status, created_at)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_evidence_investigation_created_at "
            "ON evidence (investigation_id, created_at)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_idempotency_keys_created_at "
            "ON idempotency_keys (created_at)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_idempotency_keys_created_at"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_evidence_investigation_created_at"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_investigations_status_created_at"))
