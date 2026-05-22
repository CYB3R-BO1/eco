"""Phase 6 WP11 — DLQ depth gauge tracks reality.

Failure mode: DLQ inserts must move the ``dlq_depth`` gauge in lock-step.
If the gauge drifts (insert succeeded but gauge unchanged) operators
won't see the queue growing — silent data loss in the failure path.

This test seeds entries through ``DeadLetterStore`` and reads
``DLQ_DEPTH.labels(queue_name=...).gauge.get()`` between every insert.
Requires the full compose stack so the store actually writes to
Postgres.
"""
from __future__ import annotations

import pytest

# Skip by default — chaos tests need the full docker stack.
pytestmark = [pytest.mark.chaos, pytest.mark.skip(reason="requires compose stack")]


def test_dlq_depth_gauge_tracks_inserts() -> None:
    pytest.skip("scaffold — implement once compose-backed harness lands")
