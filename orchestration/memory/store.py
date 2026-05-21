"""InvestigationMemory — Redis-backed bounded short-term memory.

Per PLAN.md §3 "Bounded AI Memory":

- Investigation-scoped: every method is keyed by the ``investigation_id``
  baked into the instance at construction; cross-investigation access is
  structurally impossible.
- TTL: ``memory_ttl_seconds`` (default 3600). Renewed on every append.
- Depth cap: ``max_memory_depth`` (default 50) entries — FIFO eviction via
  ``LTRIM``. The oldest entry is discarded silently (event emission is the
  caller's job, not the store's, so the store stays infrastructure-only).
- Per-entry token cap: ``max_tokens_per_memory`` (default 2048). Summaries
  over the cap are truncated and ``truncated=True`` is stamped on the
  stored entry — the agent runtime emits ``MEMORY_ENTRY_TRUNCATED``.
- Total-token cap: ``max_total_tokens`` (default 16384). Exceeding it
  raises :class:`MemoryBudgetExceeded`; the agent runtime catches this and
  routes the workflow to ``REVIEW_REQUIRED``.
- Relevance filter: deterministic Jaccard over normalized token sets
  (see :func:`orchestration.memory.entry.jaccard_relevance`).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import structlog

from core.cache.redis import RedisClient
from core.config.settings import OrchestrationSettings
from core.llm.tokens import estimate_tokens
from orchestration.memory.entry import MemoryEntry, jaccard_relevance

log = structlog.get_logger(__name__)


class MemoryBudgetExceeded(Exception):
    """Raised by :meth:`InvestigationMemory.append` when total tokens would
    exceed ``max_total_tokens``. Callers route the workflow to
    ``REVIEW_REQUIRED``; they do not silently drop entries.
    """

    def __init__(self, investigation_id: uuid.UUID, used: int, cap: int) -> None:
        super().__init__(
            f"investigation {investigation_id} memory budget exceeded: "
            f"used={used} cap={cap}"
        )
        self.investigation_id = investigation_id
        self.used = used
        self.cap = cap


@dataclass(frozen=True)
class MemoryAppendResult:
    entry: MemoryEntry
    truncated: bool
    evicted: int           # entries removed by FIFO depth cap (0 or 1 per append)
    total_tokens: int      # running total after this append


def _entries_key(investigation_id: uuid.UUID) -> str:
    return f"memory:investigation:{investigation_id}"


def _tokens_key(investigation_id: uuid.UUID) -> str:
    return f"memory:investigation:{investigation_id}:tokens"


class InvestigationMemory:
    """Investigation-scoped memory. One instance per investigation_id."""

    def __init__(
        self,
        *,
        redis: RedisClient,
        settings: OrchestrationSettings,
        investigation_id: uuid.UUID,
    ) -> None:
        self._redis = redis
        self._settings = settings
        self._investigation_id = investigation_id

    @property
    def investigation_id(self) -> uuid.UUID:
        return self._investigation_id

    async def append(self, entry: MemoryEntry) -> MemoryAppendResult:
        if entry.investigation_id != self._investigation_id:
            raise ValueError(
                "MemoryEntry.investigation_id does not match this memory's scope"
            )

        truncated, summary = self._maybe_truncate(entry.summary)
        if truncated:
            entry = MemoryEntry(
                entry_id=entry.entry_id,
                investigation_id=entry.investigation_id,
                agent_name=entry.agent_name,
                summary=summary,
                payload=entry.payload,
                tokens=estimate_tokens(summary),
                created_at=entry.created_at,
                truncated=True,
            )

        client = self._redis.client
        entries_key = _entries_key(self._investigation_id)
        tokens_key = _tokens_key(self._investigation_id)
        ttl = self._settings.memory_ttl_seconds

        # Pre-flight: would this push us over the total-token cap?
        used_raw = await client.get(tokens_key)
        used = int(used_raw) if used_raw is not None else 0
        if used + entry.tokens > self._settings.max_total_tokens:
            raise MemoryBudgetExceeded(
                self._investigation_id,
                used + entry.tokens,
                self._settings.max_total_tokens,
            )

        payload = json.dumps(entry.to_dict()).encode("utf-8")
        async with client.pipeline(transaction=True) as pipe:
            pipe.lpush(entries_key, payload)
            pipe.ltrim(entries_key, 0, self._settings.max_memory_depth - 1)
            pipe.llen(entries_key)
            pipe.incrby(tokens_key, entry.tokens)
            pipe.expire(entries_key, ttl)
            pipe.expire(tokens_key, ttl)
            results = await pipe.execute()

        new_len = int(results[2])
        new_total = int(results[3])

        # FIFO eviction: if the list was already full and LTRIM dropped one
        # entry, len equals depth cap and a prior length must have been > cap.
        # We can't observe that pre-state cheaply; the caller treats this
        # field as 0 or 1 per append. Reasonable approximation:
        evicted = 1 if new_len == self._settings.max_memory_depth and new_total != entry.tokens else 0

        log.debug(
            "memory.append",
            investigation_id=str(self._investigation_id),
            agent=entry.agent_name,
            tokens=entry.tokens,
            truncated=truncated,
            new_total_tokens=new_total,
            depth=new_len,
        )
        return MemoryAppendResult(
            entry=entry,
            truncated=truncated,
            evicted=evicted,
            total_tokens=new_total,
        )

    async def recall(
        self,
        query: str,
        *,
        k: int = 5,
        min_relevance: float | None = None,
    ) -> list[MemoryEntry]:
        threshold = (
            self._settings.relevance_threshold if min_relevance is None else min_relevance
        )
        entries = await self.list()
        if not entries:
            return []
        scored = [
            (jaccard_relevance(query, e.summary), e) for e in entries
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for score, entry in scored if score >= threshold][:k]

    async def list(self) -> list[MemoryEntry]:
        client = self._redis.client
        raw_items = await client.lrange(_entries_key(self._investigation_id), 0, -1)
        return [MemoryEntry.from_dict(json.loads(item)) for item in raw_items]

    async def clear(self) -> int:
        client = self._redis.client
        entries_key = _entries_key(self._investigation_id)
        tokens_key = _tokens_key(self._investigation_id)
        async with client.pipeline(transaction=True) as pipe:
            pipe.llen(entries_key)
            pipe.delete(entries_key)
            pipe.delete(tokens_key)
            results = await pipe.execute()
        return int(results[0])

    async def total_tokens(self) -> int:
        used_raw = await self._redis.client.get(_tokens_key(self._investigation_id))
        return int(used_raw) if used_raw is not None else 0

    async def depth(self) -> int:
        return int(await self._redis.client.llen(_entries_key(self._investigation_id)))

    def _maybe_truncate(self, summary: str) -> tuple[bool, str]:
        """Truncate ``summary`` to ``max_tokens_per_memory`` chars * 4 (heuristic).

        The 4-chars-per-token heuristic matches :func:`estimate_tokens`. We
        truncate at the character boundary that brings tokens to the cap —
        cheap, deterministic, no tokenizer dependency.
        """
        cap_tokens = self._settings.max_tokens_per_memory
        if estimate_tokens(summary) <= cap_tokens:
            return False, summary
        cap_chars = cap_tokens * 4
        return True, summary[:cap_chars]
