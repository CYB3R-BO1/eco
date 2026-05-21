"""MemoryEntry — one record in an investigation's bounded memory.

Each entry carries the *summary* (short, agent-emitted) plus opaque
``payload`` (kept small by callers) and the agent that produced it.
Relevance filtering uses Jaccard similarity over normalized token sets —
deterministic, cheap, no LLM in the recall path (PLAN.md §3 prescribes
relevance filtering without specifying the algorithm; an LLM would make
recall non-deterministic and burn the per-investigation token budget).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.llm.tokens import estimate_tokens

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _normalize_tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {tok.lower() for tok in _TOKEN_RE.findall(text)}


def jaccard_relevance(query: str, candidate: str) -> float:
    """Deterministic relevance score in ``[0.0, 1.0]``.

    Returns 0 when either side has no tokens. Identical token sets score 1.
    Used by :meth:`InvestigationMemory.recall` to filter below the
    ``relevance_threshold`` from settings.
    """
    q = _normalize_tokens(query)
    c = _normalize_tokens(candidate)
    if not q or not c:
        return 0.0
    inter = len(q & c)
    union = len(q | c)
    if union == 0:
        return 0.0
    return inter / union


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: uuid.UUID
    investigation_id: uuid.UUID
    agent_name: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    truncated: bool = False

    @classmethod
    def new(
        cls,
        *,
        investigation_id: uuid.UUID,
        agent_name: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> "MemoryEntry":
        return cls(
            entry_id=uuid.uuid4(),
            investigation_id=investigation_id,
            agent_name=agent_name,
            summary=summary,
            payload=payload or {},
            tokens=estimate_tokens(summary),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": str(self.entry_id),
            "investigation_id": str(self.investigation_id),
            "agent_name": self.agent_name,
            "summary": self.summary,
            "payload": self.payload,
            "tokens": self.tokens,
            "created_at": self.created_at.isoformat(),
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        return cls(
            entry_id=uuid.UUID(data["entry_id"]),
            investigation_id=uuid.UUID(data["investigation_id"]),
            agent_name=data["agent_name"],
            summary=data["summary"],
            payload=data.get("payload", {}),
            tokens=int(data.get("tokens", 0)),
            created_at=datetime.fromisoformat(data["created_at"]),
            truncated=bool(data.get("truncated", False)),
        )
