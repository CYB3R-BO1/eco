"""Fail CI if SQLAlchemy models drift from the latest Alembic head.

Loads the metadata, compares it against the live DB (which CI just
upgrade-head'd into), and exits non-zero with a diff if anything moved.
This is the single safeguard against "I edited a model but forgot to
generate a migration" — the most common cause of staging-vs-prod schema
skew.
"""
from __future__ import annotations

import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from core.config.settings import get_settings
from core.database.base import Base
# Importing the model package ensures every model is registered against
# ``Base.metadata`` before we compare.
import storage.postgres.models  # noqa: F401


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.postgres.sync_dsn)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        diff = compare_metadata(context, Base.metadata)
    if diff:
        print("::error::model/metadata drift detected:")
        for entry in diff:
            print(f"  {entry!r}")
        return 1
    print("[check_migration_drift] models match alembic head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
