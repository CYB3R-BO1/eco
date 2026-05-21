"""Dead-letter queue substrate (PLAN.md §10.5).

A single ``dead_letter_entries`` table holds entries for all four logical
queues — ``ENRICHMENT``, ``GRAPH``, ``REASONING``, ``WORKFLOW`` — keyed
by ``queue_name``. :class:`DeadLetterStore` is the only writer.
:func:`replay_entry` is the admin-only manual replay tool (never on the
public API per PLAN.md "Out of scope" → "auto-replay from DLQ").
"""
from orchestration.dlq.store import DeadLetterStore, DeadLetterWriteResult, fingerprint_payload
from orchestration.dlq.replay import ReplayOutcome, ReplayResult, replay_entry

__all__ = [
    "DeadLetterStore",
    "DeadLetterWriteResult",
    "ReplayOutcome",
    "ReplayResult",
    "fingerprint_payload",
    "replay_entry",
]
