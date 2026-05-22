"""Retention + maintenance jobs (Phase 6 WP6).

Each module exports ``async def run(database, settings) -> JobResult`` so
the scheduler factory can wire them by name. Jobs are idempotent: a
second invocation produces the same end state (zero deletions on the
second pass because the cutoff window slides forward by one tick).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobResult:
    """Returned by every retention job.

    ``deleted`` is the row count actually removed (or that would have
    been removed in dry-run mode). ``dry_run`` mirrors the setting at
    invocation time so the metric label is unambiguous.
    """

    job_name: str
    deleted: int
    dry_run: bool
    error: str | None = None

    @property
    def outcome(self) -> str:
        if self.error:
            return "error"
        return "dry_run" if self.dry_run else "success"
