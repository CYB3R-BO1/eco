"""Embedded retention + maintenance scheduler (Phase 6 WP6).

The scheduler runs INSIDE the API process — modular monolith principle
from CLAUDE.md. Per-job advisory locks (see :mod:`core.scheduler.locks`)
mean a multi-worker uvicorn deployment won't fan out the cron — exactly
one worker fires each tick.

``APScheduler`` is the runtime (already a stable, async-friendly
dependency). The factory in :func:`build_scheduler` is the only place
that imports the library so unit tests that don't care about scheduling
don't need the dependency installed.
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


def build_scheduler() -> Any | None:
    """Return a configured :class:`AsyncIOScheduler` or ``None`` if the
    optional ``apscheduler`` dependency is missing.

    Returning ``None`` keeps the no-op path explicit at the call site so
    tests without the dependency installed still pass — production
    deployments install ``apscheduler`` and get the real scheduler.

    Phase 7 WP3: a missing ``apscheduler`` in production means retention
    jobs never run — a silent data-growth regression. We escalate from
    INFO to WARNING and bump the synthetic
    ``retention_job_runs_total{job="scheduler_disabled",outcome="error"}``
    counter once so an operator alert fires on first boot.
    """
    try:
        from apscheduler.schedulers.asyncio import (  # type: ignore[import-not-found]
            AsyncIOScheduler,
        )
    except ImportError:
        log.warning(
            "scheduler.disabled.apscheduler_unavailable",
            impact="retention jobs will NOT run",
            fix="add `apscheduler>=3.10` to runtime deps",
        )
        try:
            from core.observability.metrics import RETENTION_JOB_RUNS_TOTAL

            RETENTION_JOB_RUNS_TOTAL.labels(
                job="scheduler_disabled", outcome="error"
            ).inc()
        except Exception:  # noqa: BLE001 — metric infra optional too
            pass
        return None
    return AsyncIOScheduler()


__all__ = ["build_scheduler"]
