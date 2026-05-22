"""Provenance-tiered evidence retention (Phase 6 WP6).

CLAUDE.md invariant #12: retention TTL depends on provenance level —
PRIMARY_SOURCE rows live longest, AI_GENERATED rows shortest. This job
sweeps each level in one round-trip, emits ``retention_job_runs_total``,
and respects the ``dry_run`` flag in settings.

The DELETE goes through a single SQL statement with a CTE so the row
count is reported as part of the same transaction — the alternative
(SELECT then DELETE) races with concurrent INSERTs.
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
    from core.database.postgres import Database

log = structlog.get_logger(__name__)

JOB_NAME = "retention_evidence"

# Map provenance level → setting attribute. Adding a level here is a code
# change reviewable in a diff (intentional — retention rules are a security
# concern, not config-loaded data).
_LEVELS: tuple[tuple[str, str], ...] = (
    ("PRIMARY_SOURCE", "evidence_primary_days"),
    ("DERIVED_SOURCE", "evidence_derived_days"),
    ("THIRD_PARTY", "evidence_third_party_days"),
    ("AI_GENERATED", "evidence_ai_generated_days"),
    ("USER_SUPPLIED", "evidence_user_supplied_days"),
)


async def run(database, settings: RetentionSettings) -> JobResult:  # type: ignore[no-untyped-def]
    total_deleted = 0
    error: str | None = None
    async with database.session() as session:
        async with job_lock(session, JOB_NAME) as held:
            if not held:
                return JobResult(JOB_NAME, deleted=0, dry_run=settings.dry_run)
            try:
                for level, attr in _LEVELS:
                    days = getattr(settings, attr)
                    deleted = await _sweep_level(
                        session, level, days, dry_run=settings.dry_run
                    )
                    total_deleted += deleted
                    log.info(
                        "retention.evidence.swept",
                        level=level,
                        days=days,
                        deleted=deleted,
                        dry_run=settings.dry_run,
                    )
                if not settings.dry_run:
                    await session.commit()
            except Exception as exc:  # noqa: BLE001 — propagate as JobResult.error
                error = f"{type(exc).__name__}: {exc}"
                log.exception("retention.evidence.failed")
                await session.rollback()

    result = JobResult(JOB_NAME, deleted=total_deleted, dry_run=settings.dry_run, error=error)
    RETENTION_JOB_RUNS_TOTAL.labels(job=JOB_NAME, outcome=result.outcome).inc()
    return result


async def _sweep_level(session, level: str, days: int, *, dry_run: bool) -> int:  # type: ignore[no-untyped-def]
    cutoff_clause = f"now() - interval '{int(days)} days'"
    if dry_run:
        stmt = text(
            f"SELECT count(*) FROM evidence "
            f"WHERE provenance->>'level' = :level AND created_at < {cutoff_clause}"
        )
        result = await session.execute(stmt, {"level": level})
        return int(result.scalar() or 0)
    stmt = text(
        f"WITH deleted AS ("
        f"  DELETE FROM evidence "
        f"  WHERE provenance->>'level' = :level AND created_at < {cutoff_clause} "
        f"  RETURNING 1"
        f") SELECT count(*) FROM deleted"
    )
    result = await session.execute(stmt, {"level": level})
    return int(result.scalar() or 0)
