"""DLQ retention (Phase 6 WP6).

Purges resolved ``dead_letter_entries`` rows older than
``settings.dlq_resolved_days``. Unresolved rows are NEVER deleted — they
represent un-replayed failures that an operator still needs to triage.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from core.observability.metrics import RETENTION_JOB_RUNS_TOTAL
from core.scheduler.jobs import JobResult
from core.scheduler.locks import job_lock

if TYPE_CHECKING:
    from core.config.settings import RetentionSettings

log = structlog.get_logger(__name__)

JOB_NAME = "retention_dlq"


async def run(database, settings: RetentionSettings) -> JobResult:  # type: ignore[no-untyped-def]
    deleted = 0
    error: str | None = None
    cutoff_clause = f"now() - interval '{int(settings.dlq_resolved_days)} days'"
    async with database.session() as session:
        async with job_lock(session, JOB_NAME) as held:
            if not held:
                return JobResult(JOB_NAME, deleted=0, dry_run=settings.dry_run)
            try:
                where = f"replayed_at IS NOT NULL AND replayed_at < {cutoff_clause}"
                if settings.dry_run:
                    result = await session.execute(
                        text(f"SELECT count(*) FROM dead_letter_entries WHERE {where}")
                    )
                else:
                    result = await session.execute(
                        text(
                            f"WITH d AS ("
                            f"  DELETE FROM dead_letter_entries WHERE {where} "
                            f"  RETURNING 1"
                            f") SELECT count(*) FROM d"
                        )
                    )
                deleted = int(result.scalar() or 0)
                if not settings.dry_run:
                    await session.commit()
                log.info(
                    "retention.dlq.swept",
                    days=settings.dlq_resolved_days,
                    deleted=deleted,
                    dry_run=settings.dry_run,
                )
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log.exception("retention.dlq.failed")
                await session.rollback()

    result_obj = JobResult(JOB_NAME, deleted=deleted, dry_run=settings.dry_run, error=error)
    RETENTION_JOB_RUNS_TOTAL.labels(job=JOB_NAME, outcome=result_obj.outcome).inc()
    return result_obj
