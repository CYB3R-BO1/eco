"""Phase 7 WP2 — retention_idempotency contract test.

End-to-end behaviour requires a live Postgres (handled in integration
tests). This unit-level test pins the surface:

- The job is registered with a stable name.
- ``RetentionSettings.idempotency_keys_hours`` is the knob.
- ``run`` returns a :class:`JobResult` and never raises (errors land on
  ``JobResult.error``).
- The metric label set is correct.
"""
from __future__ import annotations

import pytest

from core.config.settings import RetentionSettings
from core.observability.metrics import RETENTION_JOB_RUNS_TOTAL
from core.scheduler.jobs import retention_idempotency


def test_job_name_is_stable() -> None:
    assert retention_idempotency.JOB_NAME == "retention_idempotency"


def test_retention_settings_has_idempotency_knob() -> None:
    s = RetentionSettings()
    assert isinstance(s.idempotency_keys_hours, int)
    assert s.idempotency_keys_hours == 24


def test_metric_is_registered_for_the_new_job() -> None:
    # Touch the labels to assert the metric accepts them. If a future
    # change drops ``job`` or ``outcome`` from the label set, this fails.
    counter = RETENTION_JOB_RUNS_TOTAL.labels(
        job=retention_idempotency.JOB_NAME, outcome="dry_run"
    )
    assert counter is not None


@pytest.mark.asyncio
async def test_run_returns_jobresult_when_db_unavailable() -> None:
    """The job must not raise; failures become ``JobResult.error``.

    We stub ``database.session()`` to a context manager whose execute
    raises. The job swallows it, rolls back, and reports the error in
    the returned ``JobResult`` so the scheduler doesn't lose track.
    """

    class _BadSession:
        async def __aenter__(self) -> "_BadSession":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("simulated db outage")

        async def rollback(self) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _BadDatabase:
        def session(self) -> _BadSession:
            return _BadSession()

    result = await retention_idempotency.run(
        _BadDatabase(),  # type: ignore[arg-type]
        RetentionSettings(dry_run=True),
    )
    # advisory-lock query is the first execute call — it raises, the
    # job catches, returns an error JobResult.
    assert result.job_name == "retention_idempotency"
    assert result.error is not None
    assert "simulated db outage" in result.error
