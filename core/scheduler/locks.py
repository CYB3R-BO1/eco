"""Per-job Postgres advisory locks (Phase 6 WP6).

Two uvicorn workers will both wake up on each cron tick. Without
coordination, both would run the retention DELETE — at best duplicating
work, at worst racing on the same rows. Postgres' session-scoped
advisory locks are the right primitive for "exactly one worker per
tick": cheap (in-memory), no FK pressure, scoped to the database
connection so a crashed worker frees the lock automatically.

Job names hash to a stable ``bigint`` so the lock key is deterministic
across deploys but invisible outside this module — callers pass a
human-readable job name.
"""
from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


def _job_lock_key(job_name: str) -> int:
    """Hash a job name to a signed 64-bit int.

    Postgres ``pg_try_advisory_lock(bigint)`` accepts a signed 8-byte
    integer; SHA-256 → first 8 bytes → big-endian signed int.
    """
    digest = hashlib.sha256(job_name.encode("utf-8")).digest()[:8]
    value = int.from_bytes(digest, byteorder="big", signed=False)
    # Map into signed-bigint range without changing the bits we care
    # about (Postgres treats the lock key as opaque, so wrap is fine).
    return value - (1 << 64) if value >= (1 << 63) else value


@asynccontextmanager
async def job_lock(
    session: AsyncSession, job_name: str
) -> AsyncIterator[bool]:
    """Try to acquire the advisory lock for ``job_name``.

    Yields ``True`` if this caller holds the lock for the duration of
    the context, ``False`` if another worker beat us to it. The lock
    is released on context exit by ``pg_advisory_unlock`` — and also by
    Postgres if the session terminates, so a crash can't leave a stuck
    lock.
    """
    key = _job_lock_key(job_name)
    result = await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
    acquired = bool(result.scalar())
    if not acquired:
        log.debug("scheduler.lock.skipped", job=job_name)
        yield False
        return
    log.debug("scheduler.lock.acquired", job=job_name)
    try:
        yield True
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        log.debug("scheduler.lock.released", job=job_name)
