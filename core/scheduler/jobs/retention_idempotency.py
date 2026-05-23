"""``idempotency_keys`` retention (Phase 7 WP2).

The Phase 2 docstring on :class:`IdempotencyKeyRow` promised "a scheduled
job in a later phase will prune entries older than ~24h". This is that
job. Stale idempotency rows are deleted; the matching HTTP-cache entry
in Redis ages out on its own TTL.

Same shape as the other retention jobs: advisory-locked, dry-run aware,
emits ``retention_job_runs_total``.
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

JOB_NAME = "retention_idempotency"


async def run(database, settings: RetentionSettings) -> JobResult:  # type: ignore[no-untyped-def]
    deleted = 0
    error: str | None = None
    cutoff_clause = (
        f"now() - interval '{int(settings.idempotency_keys_hours)} hours'"
    )
    async with database.session() as session:
        async with job_lock(session, JOB_NAME) as held:
            if not held:
                return JobResult(JOB_NAME, deleted=0, dry_run=settings.dry_run)
            try:
                if settings.dry_run:
                    result = await session.execute(
                        text(
                            f"SELECT count(*) FROM idempotency_keys "
                            f"WHERE created_at < {cutoff_clause}"
                        )
                    )
                else:
                    result = await session.execute(
                        text(
                            f"WITH d AS ("
                            f"  DELETE FROM idempotency_keys "
                            f"  WHERE created_at < {cutoff_clause} "
                            f"  RETURNING 1"
                            f") SELECT count(*) FROM d"
                        )
                    )
                deleted = int(result.scalar() or 0)
                if not settings.dry_run:
                    await session.commit()
                log.info(
                    "retention.idempotency.swept",
                    hours=settings.idempotency_keys_hours,
                    deleted=deleted,
                    dry_run=settings.dry_run,
                )
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log.exception("retention.idempotency.failed")
                await session.rollback()

    result_obj = JobResult(
        JOB_NAME, deleted=deleted, dry_run=settings.dry_run, error=error
    )
    RETENTION_JOB_RUNS_TOTAL.labels(
        job=JOB_NAME, outcome=result_obj.outcome
    ).inc()
    return result_obj
