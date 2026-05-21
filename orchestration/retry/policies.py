"""RetryPolicy — per-surface retry knobs (PLAN.md §10.5).

Four flavors:

- **enrichment**: exponential backoff (base 2s, cap 60s), 3 attempts.
- **graph**: linear backoff (1s, 2s), 2 attempts (graph is append-only —
  retries are cheap, but we keep counts low so post-retry failures route
  to ``graph_dlq`` quickly).
- **ai**: exponential backoff (base 1s, cap 8s), 2 attempts — LLM calls
  must fail fast; the workflow continues with a deterministic summary.
- **workflow**: no retry at the top level; an uncaught exception inside
  a node lands in ``workflow_dlq`` directly.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class BackoffKind(str, enum.Enum):
    NONE = "NONE"
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"


@dataclass(frozen=True)
class RetryPolicy:
    name: str
    max_attempts: int
    backoff: BackoffKind
    base_seconds: float
    cap_seconds: float
    jitter_seconds: float = 0.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Return the delay before *attempt n* (1-indexed)."""
        if attempt <= 1 or self.backoff is BackoffKind.NONE:
            return 0.0
        if self.backoff is BackoffKind.LINEAR:
            delay = self.base_seconds * (attempt - 1)
        else:  # EXPONENTIAL
            delay = self.base_seconds * (2 ** (attempt - 2))
        return min(delay, self.cap_seconds)


DEFAULT_ENRICHMENT_POLICY = RetryPolicy(
    name="enrichment",
    max_attempts=3,
    backoff=BackoffKind.EXPONENTIAL,
    base_seconds=2.0,
    cap_seconds=60.0,
    jitter_seconds=0.25,
)

DEFAULT_GRAPH_POLICY = RetryPolicy(
    name="graph",
    max_attempts=2,
    backoff=BackoffKind.LINEAR,
    base_seconds=1.0,
    cap_seconds=5.0,
)

DEFAULT_AI_POLICY = RetryPolicy(
    name="ai",
    max_attempts=2,
    backoff=BackoffKind.EXPONENTIAL,
    base_seconds=1.0,
    cap_seconds=8.0,
)

DEFAULT_WORKFLOW_POLICY = RetryPolicy(
    name="workflow",
    max_attempts=1,
    backoff=BackoffKind.NONE,
    base_seconds=0.0,
    cap_seconds=0.0,
)
