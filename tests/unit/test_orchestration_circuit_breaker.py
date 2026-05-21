"""CircuitBreaker FSM: closed → open → half-open → closed."""
from __future__ import annotations

import asyncio
import time

import pytest

from orchestration.retry.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


@pytest.mark.asyncio
async def test_starts_closed() -> None:
    cb = CircuitBreaker(
        "agent:x", open_after_failures=3, window_seconds=60, open_duration_seconds=1
    )
    assert cb.state == CircuitState.CLOSED
    await cb.check()  # does not raise


@pytest.mark.asyncio
async def test_opens_after_threshold_failures() -> None:
    cb = CircuitBreaker(
        "agent:x", open_after_failures=3, window_seconds=60, open_duration_seconds=60
    )
    for _ in range(3):
        await cb.on_failure()
    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await cb.check()


@pytest.mark.asyncio
async def test_transitions_to_half_open_after_duration() -> None:
    cb = CircuitBreaker(
        "agent:x",
        open_after_failures=2,
        window_seconds=60,
        open_duration_seconds=0,  # immediate transition for the test
    )
    for _ in range(2):
        await cb.on_failure()
    assert cb.state == CircuitState.OPEN
    # check() flips OPEN → HALF_OPEN once enough time has elapsed.
    await cb.check()
    assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_to_closed_on_success() -> None:
    cb = CircuitBreaker(
        "agent:x",
        open_after_failures=2,
        window_seconds=60,
        open_duration_seconds=0,
    )
    await cb.on_failure()
    await cb.on_failure()
    await cb.check()
    assert cb.state == CircuitState.HALF_OPEN
    await cb.on_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_to_open_on_failure() -> None:
    cb = CircuitBreaker(
        "agent:x",
        open_after_failures=2,
        window_seconds=60,
        open_duration_seconds=0,
    )
    await cb.on_failure()
    await cb.on_failure()
    await cb.check()
    assert cb.state == CircuitState.HALF_OPEN
    await cb.on_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_failures_outside_window_dont_trip() -> None:
    cb = CircuitBreaker(
        "agent:x",
        open_after_failures=3,
        window_seconds=0,  # all failures fall outside the window immediately
        open_duration_seconds=60,
    )
    for _ in range(10):
        await cb.on_failure()
        # Each call's prior failures are evicted because window=0.
    # Threshold counts only failures *within* the window; here that's the one
    # we just recorded, so we should still be closed.
    assert cb.state == CircuitState.CLOSED
