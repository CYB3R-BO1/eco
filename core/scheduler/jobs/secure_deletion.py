"""Process the secure-deletion queue (Phase 6 WP6).

The firewall enqueues rows into ``secure_deletion_queue`` when sensitive
data (leaked API keys, PII bursts) is detected. This job runs every
``secure_deletion_interval_seconds`` ticks, deletes the targeted rows,
and marks the queue entry as processed.

Why a queue and not direct delete from the firewall: invariant #6 says
the graph is append-only — the firewall can't reach into graph or
evidence storage to remove rows itself. The queue decouples detection
from deletion so the secure-deletion job is the SINGLE auditable point
where rows leave the platform.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from core.observability.metrics import RETENTION_JOB_RUNS_TOTAL
from core.scheduler.jobs import JobResult
from core.scheduler.locks import job_lock

if TYPE_CHECKING:
    from core.config.settings import RetentionSettings

log = structlog.get_logger(__name__)

JOB_NAME = "secure_deletion"

# Whitelist the tables this job is allowed to touch. The firewall might
# enqueue a typo'd table name — silently deleting from an unrelated table
# would be a serious bug. Anything not in this allow-list is logged and
# left in the queue with ``error`` set.
_ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "evidence",
        "firewall_events",
        "memory_audits",
        "enrichment_results",
    }
)


async def run(database, settings: RetentionSettings) -> JobResult:  # type: ignore[no-untyped-def]
    processed = 0
    error: str | None = None
    async with database.session() as session:
        async with job_lock(session, JOB_NAME) as held:
            if not held:
                return JobResult(JOB_NAME, deleted=0, dry_run=False)
            try:
                rows = (
                    await session.execute(
                        text(
                            "SELECT id, target_table, target_row_id, reason "
                            "FROM secure_deletion_queue "
                            "WHERE processed_at IS NULL "
                            "ORDER BY enqueued_at "
                            "LIMIT 100"
                        )
                    )
                ).all()
                now = datetime.now(timezone.utc)
                for row in rows:
                    queue_id, table, target_id, reason = row
                    if table not in _ALLOWED_TABLES:
                        await session.execute(
                            text(
                                "UPDATE secure_deletion_queue "
                                "SET processed_at = :now, processor = :who, error = :err "
                                "WHERE id = :id"
                            ),
                            {
                                "now": now,
                                "who": JOB_NAME,
                                "err": f"table {table!r} not allow-listed",
                                "id": queue_id,
                            },
                        )
                        log.warning(
                            "secure_deletion.rejected_table",
                            table=table,
                            queue_id=str(queue_id),
                        )
                        continue
                    # Parameterized table name is unsafe (SQL injection); we
                    # explicitly validated against the allow-list above.
                    await session.execute(
                        text(f"DELETE FROM {table} WHERE id = :id"),
                        {"id": target_id},
                    )
                    await session.execute(
                        text(
                            "UPDATE secure_deletion_queue "
                            "SET processed_at = :now, processor = :who "
                            "WHERE id = :id"
                        ),
                        {"now": now, "who": JOB_NAME, "id": queue_id},
                    )
                    processed += 1
                    log.info(
                        "secure_deletion.processed",
                        table=table,
                        target_id=str(target_id),
                        reason=reason,
                    )
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log.exception("secure_deletion.failed")
                await session.rollback()

    result_obj = JobResult(
        JOB_NAME, deleted=processed, dry_run=False, error=error
    )
    RETENTION_JOB_RUNS_TOTAL.labels(job=JOB_NAME, outcome=result_obj.outcome).inc()
    return result_obj
