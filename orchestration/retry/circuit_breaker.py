"""CircuitBreaker — three-state breaker per ``(agent, target_service)``.

States (PLAN.md §10.5):

- **Closed**: requests flow normally. Failures within ``window_seconds``
  count toward the trip threshold.
- **Open**: requests fail fast with :class:`CircuitOpenError`. After
  ``open_duration_seconds`` we transition to Half-Open.
- **Half-Open**: one probe request is allowed; success → Closed, failure
  → Open again.

State is held in-process. A multi-worker deployment would want Redis-
backed state, but Phase 5 ships a single-process orchestration runtime
(see PLAN.md "Out of scope"). The breaker is intentionally simple — it is
a back-pressure guard, not a consensus protocol.
"""
from __future__ import annotations

import asyncio
import enum
import time
from dataclasses import dataclass, field

import structlog

from core.observability.metrics import CIRCUIT_BREAKER_STATE

log = structlog.get_logger(__name__)

_STATE_VALUES: dict[str, int] = {
    "CLOSED": 0,
    "HALF_OPEN": 1,
    "OPEN": 2,
}


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    def __init__(self, key: str, opened_at: float) -> None:
        super().__init__(f"circuit '{key}' is open since {opened_at:.3f}")
        self.key = key
        self.opened_at = opened_at


@dataclass
class _CircuitStateRecord:
    state: CircuitState = CircuitState.CLOSED
    failures: list[float] = field(default_factory=list)
    opened_at: float | None = None
    last_failure_at: float | None = None


class CircuitBreaker:
    """One breaker per (agent_name, target_service) key."""

    def __init__(
        self,
        key: str,
        *,
        open_after_failures: int,
        window_seconds: int,
        open_duration_seconds: int,
    ) -> None:
        self._key = key
        self._open_after = open_after_failures
        self._window = float(window_seconds)
        self._open_duration = float(open_duration_seconds)
        self._record = _CircuitStateRecord()
        self._lock = asyncio.Lock()

    @property
    def key(self) -> str:
        return self._key

    @property
    def state(self) -> CircuitState:
        return self._record.state

    def _publish_state(self) -> None:
        CIRCUIT_BREAKER_STATE.labels(agent_name=self._key).set(
            _STATE_VALUES[self._record.state.value]
        )

    async def check(self) -> None:
        """Raise :class:`CircuitOpenError` if the breaker is open."""
        async with self._lock:
            now = time.monotonic()
            if self._record.state is CircuitState.OPEN:
                assert self._record.opened_at is not None
                if now - self._record.opened_at >= self._open_duration:
                    self._record.state = CircuitState.HALF_OPEN
                    log.info("circuit.half_open", key=self._key)
                    self._publish_state()
                else:
                    raise CircuitOpenError(self._key, self._record.opened_at)

    async def on_success(self) -> None:
        async with self._lock:
            previous = self._record.state
            self._record.state = CircuitState.CLOSED
            self._record.failures.clear()
            self._record.opened_at = None
            if previous is not CircuitState.CLOSED:
                log.info("circuit.closed", key=self._key, from_state=previous.value)
            self._publish_state()

    async def on_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._record.last_failure_at = now
            if self._record.state is CircuitState.HALF_OPEN:
                self._record.state = CircuitState.OPEN
                self._record.opened_at = now
                log.warning("circuit.reopened_from_half_open", key=self._key)
                self._publish_state()
                return
            self._record.failures.append(now)
            cutoff = now - self._window
            self._record.failures = [t for t in self._record.failures if t >= cutoff]
            if len(self._record.failures) >= self._open_after:
                self._record.state = CircuitState.OPEN
                self._record.opened_at = now
                log.warning(
                    "circuit.opened",
                    key=self._key,
                    failures=len(self._record.failures),
                    window_seconds=self._window,
                )
                self._publish_state()


class CircuitBreakerRegistry:
    """Process-wide registry. One :class:`CircuitBreaker` per logical key."""

    def __init__(
        self,
        *,
        open_after_failures: int,
        window_seconds: int,
        open_duration_seconds: int,
    ) -> None:
        self._defaults = (open_after_failures, window_seconds, open_duration_seconds)
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> CircuitBreaker:
        async with self._lock:
            breaker = self._breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(
                    key,
                    open_after_failures=self._defaults[0],
                    window_seconds=self._defaults[1],
                    open_duration_seconds=self._defaults[2],
                )
                self._breakers[key] = breaker
            return breaker
