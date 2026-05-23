"""Run every retention job in dry-run mode and print the planned counts.

Operators run this before flipping ``RETENTION_DRY_RUN=false`` in
production to confirm the WHERE clauses behave as expected on the live
data set.
"""
from __future__ import annotations

import asyncio
import sys

from core.config.settings import get_settings
from core.database.postgres import Database
from core.scheduler.jobs import (
    retention_dlq,
    retention_events,
    retention_evidence,
    retention_idempotency,
)


async def main() -> int:
    settings = get_settings()
    # Force dry-run regardless of environment.
    retention = settings.retention.model_copy(update={"dry_run": True})

    db = Database(settings.postgres)
    await db.connect()
    try:
        results = []
        for job in (
            retention_evidence,
            retention_events,
            retention_dlq,
            retention_idempotency,
        ):
            result = await job.run(db, retention)
            results.append(result)
            print(
                f"[{result.job_name}] would_delete={result.deleted} "
                f"outcome={result.outcome} error={result.error}"
            )
    finally:
        await db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
