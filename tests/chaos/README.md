# Chaos tests

In-repo failure-injection tests. Each test simulates a real production
failure and asserts the platform degrades cleanly rather than corrupting
state.

| File                              | Failure mode                                              |
|-----------------------------------|-----------------------------------------------------------|
| `test_workflow_replay_safety.py`  | Kill workflow mid-run, restart from checkpointer          |
| `test_redis_outage.py`            | Pause Redis container, expect circuit-breaker open        |
| `test_neo4j_outage.py`            | Drop Neo4j connections, expect graph writes fail cleanly  |
| `test_dlq_drain.py`               | Fill DLQ, assert `dlq_depth` gauge tracks                 |

These tests require the full docker-compose stack. Marked
``@pytest.mark.chaos`` so they only run under `pytest tests/chaos` —
the standard `pytest` invocation skips them.

The chaos suite runs nightly via `.github/workflows/nightly.yml`; the
current build is advisory (failures don't block release) until the
suite stabilizes.
