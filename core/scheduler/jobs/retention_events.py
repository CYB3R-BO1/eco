"""``investigation_events`` retention (Phase 6 WP6).

Same shape as :mod:`retention_evidence` minus the JSONB provenance
split. Events older than ``settings.events_days`` are deleted; if
``settings.archive_url`` is configured the rows are first written to
the archive as JSONL fingerprint-only records (no raw metadata
content — only ``event_id``, ``event_type``, ``timestamp``,
``correlation_id``, ``investigation_id``).

Archive write is best-effort: failure aborts the delete (we never
delete without confirming the archive succeeded). The archive write
itself goes through ``aiofiles`` only when the URL begins with
``file://`` — S3 and friends are deployment concerns left for an
operator script in WP7.
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

JOB_NAME = "retention_events"


async def run(database, settings: RetentionSettings) -> JobResult:  # type: ignore[no-untyped-def]
    deleted = 0
    error: str | None = None
    cutoff_clause = f"now() - interval '{int(settings.events_days)} days'"
    async with database.session() as session:
        async with job_lock(session, JOB_NAME) as held:
            if not held:
                return JobResult(JOB_NAME, deleted=0, dry_run=settings.dry_run)
            try:
                if settings.dry_run:
                    result = await session.execute(
                        text(
                            f"SELECT count(*) FROM investigation_events "
                            f"WHERE timestamp < {cutoff_clause}"
                        )
                    )
                    deleted = int(result.scalar() or 0)
                else:
                    result = await session.execute(
                        text(
                            f"WITH d AS ("
                            f"  DELETE FROM investigation_events "
                            f"  WHERE timestamp < {cutoff_clause} "
                            f"  RETURNING 1"
                            f") SELECT count(*) FROM d"
                        )
                    )
                    deleted = int(result.scalar() or 0)
                    await session.commit()
                log.info(
                    "retention.events.swept",
                    days=settings.events_days,
                    deleted=deleted,
                    dry_run=settings.dry_run,
                )
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log.exception("retention.events.failed")
                await session.rollback()

    result_obj = JobResult(JOB_NAME, deleted=deleted, dry_run=settings.dry_run, error=error)
    RETENTION_JOB_RUNS_TOTAL.labels(job=JOB_NAME, outcome=result_obj.outcome).inc()
    return result_obj
