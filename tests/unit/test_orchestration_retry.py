"""Retry policy + decorator behavior."""
from __future__ import annotations

import asyncio

import pytest

from orchestration.retry.decorator import retry
from orchestration.retry.policies import BackoffKind, RetryPolicy


def test_exponential_backoff_caps() -> None:
    policy = RetryPolicy(
        name="x",
        max_attempts=5,
        backoff=BackoffKind.EXPONENTIAL,
        base_seconds=2.0,
        cap_seconds=10.0,
    )
    # delay before attempt 2 = base * 2^0 = 2
    # delay before attempt 3 = base * 2^1 = 4
    # delay before attempt 4 = base * 2^2 = 8
    # delay before attempt 5 = base * 2^3 = 16 → capped to 10
    assert policy.delay_for_attempt(1) == 0.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0
    assert policy.delay_for_attempt(4) == 8.0
    assert policy.delay_for_attempt(5) == 10.0


def test_linear_backoff() -> None:
    policy = RetryPolicy(
        name="x",
        max_attempts=3,
        backoff=BackoffKind.LINEAR,
        base_seconds=1.0,
        cap_seconds=5.0,
    )
    assert policy.delay_for_attempt(2) == 1.0
    assert policy.delay_for_attempt(3) == 2.0


def test_none_backoff_returns_zero() -> None:
    policy = RetryPolicy(
        name="x",
        max_attempts=3,
        backoff=BackoffKind.NONE,
        base_seconds=10.0,
        cap_seconds=10.0,
    )
    assert policy.delay_for_attempt(2) == 0.0


async def _flaky(failures_remaining: list[int]) -> str:
    if failures_remaining[0] > 0:
        failures_remaining[0] -= 1
        raise RuntimeError("transient")
    return "ok"


@pytest.mark.asyncio
async def test_retry_decorator_succeeds_within_max_attempts() -> None:
    policy = RetryPolicy(
        name="x",
        max_attempts=3,
        backoff=BackoffKind.NONE,
        base_seconds=0.0,
        cap_seconds=0.0,
    )
    state = [2]

    @retry(policy)
    async def fn() -> str:
        return await _flaky(state)

    assert await fn() == "ok"
    assert state[0] == 0


@pytest.mark.asyncio
async def test_retry_decorator_reraises_after_max_attempts() -> None:
    policy = RetryPolicy(
        name="x",
        max_attempts=2,
        backoff=BackoffKind.NONE,
        base_seconds=0.0,
        cap_seconds=0.0,
    )
    state = [5]  # never succeeds in 2 attempts

    @retry(policy)
    async def fn() -> str:
        return await _flaky(state)

    with pytest.raises(RuntimeError, match="transient"):
        await fn()
    assert state[0] == 3  # 5 - 2 attempts


@pytest.mark.asyncio
async def test_retry_calls_on_retry_callback() -> None:
    policy = RetryPolicy(
        name="x",
        max_attempts=3,
        backoff=BackoffKind.NONE,
        base_seconds=0.0,
        cap_seconds=0.0,
    )
    state = [2]
    calls: list[int] = []

    async def on_retry(attempt: int, delay: float, exc: BaseException) -> None:
        calls.append(attempt)

    @retry(policy, on_retry=on_retry)
    async def fn() -> str:
        return await _flaky(state)

    await fn()
    assert calls == [1, 2]  # called on each retry attempt
