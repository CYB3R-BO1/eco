"""@retry decorator — async-only, tenacity-backed.

Wraps a coroutine function with a :class:`RetryPolicy`. Each attempt is
logged with ``attempt``, ``next_delay_ms``, ``exception_type``. Callers
that need to emit ``AGENT_RETRY`` events do so via the ``on_retry``
callback — the decorator stays infrastructure-only and does not depend on
``EventEmitter``.
"""
from __future__ import annotations

import asyncio
import random
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

import structlog

from orchestration.retry.policies import RetryPolicy

log = structlog.get_logger(__name__)

T = TypeVar("T")

OnRetry = Callable[[int, float, BaseException], Awaitable[None]]


def retry(
    policy: RetryPolicy,
    *,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    on_retry: OnRetry | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator for async functions.

    The function is invoked up to ``policy.max_attempts`` times. Between
    attempts we ``asyncio.sleep`` for ``policy.delay_for_attempt(n)`` plus
    optional jitter. The final exception is re-raised so the caller can
    route it to a DLQ.
    """

    def wrap(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def inner(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(1, policy.max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except retry_on as exc:
                    last_exc = exc
                    if attempt >= policy.max_attempts:
                        break
                    delay = policy.delay_for_attempt(attempt + 1)
                    if policy.jitter_seconds:
                        delay += random.uniform(0.0, policy.jitter_seconds)
                    log.warning(
                        "retry.attempt",
                        policy=policy.name,
                        attempt=attempt,
                        next_delay_ms=int(delay * 1000),
                        exception_type=type(exc).__name__,
                    )
                    if on_retry is not None:
                        try:
                            await on_retry(attempt, delay, exc)
                        except Exception:
                            log.exception("retry.on_retry_callback_failed")
                    if delay > 0:
                        await asyncio.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return inner

    return wrap
