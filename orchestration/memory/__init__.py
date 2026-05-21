"""Investigation-scoped bounded memory (PLAN.md §3 "Bounded AI Memory").

Public surface:

- :class:`MemoryEntry` — one append-only record (summary text + metadata).
- :class:`InvestigationMemory` — Redis-backed bounded list keyed by
  ``investigation_id``. Depth cap, per-entry token cap, total-token cap,
  TTL, and deterministic relevance filter.
- :class:`MemoryAuditLogger` — Postgres-backed audit trail; stores SHA-256
  fingerprints only (CLAUDE.md invariant #12).
"""
from orchestration.memory.audit import MemoryAuditLogger, MemoryOperation
from orchestration.memory.entry import MemoryEntry, jaccard_relevance
from orchestration.memory.store import (
    InvestigationMemory,
    MemoryAppendResult,
    MemoryBudgetExceeded,
)

__all__ = [
    "InvestigationMemory",
    "MemoryAppendResult",
    "MemoryAuditLogger",
    "MemoryBudgetExceeded",
    "MemoryEntry",
    "MemoryOperation",
    "jaccard_relevance",
]
