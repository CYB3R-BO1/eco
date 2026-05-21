"""Per-investigation LLM token budget.

Enforces ``PLAN.md`` §3.5 ``ai.max_tokens_per_investigation``. The budget is
backed by Redis (counter keyed by investigation_id with TTL) so concurrent
agent runs against the same investigation can't race past the limit.

The check is **pre-call**: agents call ``reserve(estimated)`` *before*
sending the prompt; on a successful completion they call ``commit(actual)``
to reconcile the estimate with the provider's reported usage. If a call
fails after a reservation, ``release(estimated)`` returns the budget. This
matches the "two-phase counter" pattern used by other systems with hard
spend ceilings.
"""
from __future__ import annotations

import uuid

import structlog

from core.cache.redis import RedisClient

log = structlog.get_logger(__name__)

_KEY_TEMPLATE = "llm:budget:investigation:{id}"
_TTL_SECONDS = 24 * 3600  # ample wall-clock; investigation lifecycle bounds the real lifetime


class TokenBudgetExceeded(Exception):
    """Raised by reserve() when the requested allocation would breach the budget."""

    def __init__(self, investigation_id: uuid.UUID, requested: int, remaining: int) -> None:
        self.investigation_id = investigation_id
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"token budget exceeded for investigation {investigation_id}: "
            f"requested={requested} remaining={remaining}"
        )


class InvestigationTokenBudget:
    """Process-shared budget tracker. Constructed once at app startup."""

    def __init__(self, redis: RedisClient, *, max_tokens_per_investigation: int) -> None:
        self._redis = redis
        self._max = max_tokens_per_investigation

    @property
    def max_tokens(self) -> int:
        return self._max

    def _key(self, investigation_id: uuid.UUID) -> str:
        return _KEY_TEMPLATE.format(id=investigation_id)

    async def used(self, investigation_id: uuid.UUID) -> int:
        raw = await self._redis.client.get(self._key(investigation_id))
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    async def remaining(self, investigation_id: uuid.UUID) -> int:
        used = await self.used(investigation_id)
        return max(0, self._max - used)

    async def reserve(self, investigation_id: uuid.UUID, requested: int) -> None:
        """Atomic incr+check. Raises TokenBudgetExceeded if over the cap."""
        if requested <= 0:
            return
        key = self._key(investigation_id)
        new_total = await self._redis.client.incrby(key, requested)
        await self._redis.client.expire(key, _TTL_SECONDS)
        if new_total > self._max:
            # roll back our reservation; raise so caller can short-circuit.
            await self._redis.client.decrby(key, requested)
            log.warning(
                "llm.budget.exceeded",
                investigation_id=str(investigation_id),
                requested=requested,
                cap=self._max,
            )
            raise TokenBudgetExceeded(
                investigation_id, requested, max(0, self._max - (new_total - requested))
            )

    async def release(self, investigation_id: uuid.UUID, amount: int) -> None:
        if amount <= 0:
            return
        await self._redis.client.decrby(self._key(investigation_id), amount)

    async def commit(
        self, investigation_id: uuid.UUID, *, reserved: int, actual: int
    ) -> None:
        """Reconcile estimate with actual provider-reported usage."""
        delta = actual - reserved
        if delta == 0:
            return
        if delta > 0:
            # We under-estimated. Charge the diff. We do NOT re-check the cap here:
            # the call already happened; we're keeping accounting honest.
            await self._redis.client.incrby(self._key(investigation_id), delta)
        else:
            await self._redis.client.decrby(self._key(investigation_id), -delta)
