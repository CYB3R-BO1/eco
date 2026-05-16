"""In-process background task runner.

Phase 2 uses ``asyncio.create_task`` with a bounded ``Semaphore`` for fan-out
of ingest → extract → enrich. This is NOT a durable queue — process restart
drops in-flight tasks. Phase 5 replaces the body of :meth:`run` with a real
enqueue (Redis streams / Celery / RQ) without changing any call site.

Bounded concurrency matches ``PLAN.md`` §3.5 (max_concurrent_executions=10).
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class BackgroundTaskRunner:
    def __init__(self, max_concurrent: int = 10) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task[Any]] = set()

    def run(self, coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any]:
        task = asyncio.create_task(self._wrap(coro), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _wrap(self, coro: Coroutine[Any, Any, Any]) -> None:
        async with self._semaphore:
            try:
                await coro
            except Exception:
                log.exception("background_task.failed")

    async def drain(self, timeout: float = 30.0) -> None:
        if not self._tasks:
            return
        done, pending = await asyncio.wait(self._tasks, timeout=timeout)
        if pending:
            log.warning("background_task.drain_timeout", pending=len(pending))
            for t in pending:
                t.cancel()
