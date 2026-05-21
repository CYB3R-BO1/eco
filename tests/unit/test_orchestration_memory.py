"""InvestigationMemory: relevance + entry helpers (Redis-independent paths).

Integration tests in ``tests/integration/test_workflow_memory_isolation.py``
cover the Redis-backed cross-investigation isolation.
"""
from __future__ import annotations

import uuid

import pytest

from orchestration.memory.entry import MemoryEntry, jaccard_relevance


def test_jaccard_identical_text() -> None:
    assert jaccard_relevance("the quick brown fox", "the quick brown fox") == 1.0


def test_jaccard_disjoint_text() -> None:
    assert jaccard_relevance("alpha beta gamma", "delta epsilon zeta") == 0.0


def test_jaccard_partial_overlap() -> None:
    score = jaccard_relevance("alpha beta", "alpha gamma")
    # tokens: {alpha, beta} vs {alpha, gamma} → intersection=1 union=3 → 1/3
    assert 0.32 < score < 0.34


def test_jaccard_empty_inputs() -> None:
    assert jaccard_relevance("", "anything") == 0.0
    assert jaccard_relevance("anything", "") == 0.0


def test_memory_entry_roundtrip() -> None:
    inv_id = uuid.uuid4()
    entry = MemoryEntry.new(
        investigation_id=inv_id,
        agent_name="enrichment",
        summary="processed 3 IOCs; provider_failures=0",
        payload={"finding_count": 3},
    )
    encoded = entry.to_dict()
    decoded = MemoryEntry.from_dict(encoded)
    assert decoded.entry_id == entry.entry_id
    assert decoded.investigation_id == inv_id
    assert decoded.summary == entry.summary
    assert decoded.payload == {"finding_count": 3}
    assert decoded.tokens > 0


def test_memory_entry_token_estimate_grows_with_text() -> None:
    short = MemoryEntry.new(
        investigation_id=uuid.uuid4(),
        agent_name="x",
        summary="hi",
    )
    long_ = MemoryEntry.new(
        investigation_id=uuid.uuid4(),
        agent_name="x",
        summary="x" * 400,
    )
    assert long_.tokens > short.tokens
