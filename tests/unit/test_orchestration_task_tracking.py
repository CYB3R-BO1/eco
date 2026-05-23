"""Phase 7 WP1 — OrchestrationService tracks background workflow tasks.

Bare ``asyncio.create_task`` lets Python GC the task mid-flight (the
infamous "Task was destroyed but it is pending" warning) AND prevents
the lifespan from draining workflows on shutdown. This test pins the
contract that every background run lands in ``service._tasks`` and is
removed on completion.

The test stubs out the LangGraph + DB collaborators so the only thing
exercised is the task-lifecycle plumbing.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from orchestration.service import OrchestrationService


class _DummyGraph:
    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        # Yield control so the task is observable as ``pending`` before
        # it completes — otherwise the test races on creation/completion.
        await asyncio.sleep(0)
        return {"final_state": "SUCCEEDED"}


class _DummyDatabase:
    def session(self):  # type: ignore[no-untyped-def]
        return _DummyDatabaseSession()


class _DummyDatabaseSession:
    async def __aenter__(self) -> "_DummyDatabaseSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        class _R:
            def scalar_one_or_none(self_inner) -> None:  # noqa: N805
                return None

        return _R()

    def add(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def get(self, *args: Any, **kwargs: Any) -> None:
        return None


class _DummyEmitter:
    async def emit(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_background_workflow_is_tracked_and_drained() -> None:
    service = OrchestrationService(
        database=_DummyDatabase(),  # type: ignore[arg-type]
        event_emitter=_DummyEmitter(),  # type: ignore[arg-type]
        graphs={"investigation": _DummyGraph()},
    )

    assert service.in_flight_count == 0

    handle = await service.run_workflow(
        workflow_name="investigation",
        inputs={"x": 1},
        background=True,
    )
    assert isinstance(handle.workflow_run_id, uuid.UUID)
    assert service.in_flight_count == 1

    # Drain should wait for the in-flight task, then the set is empty.
    await service.drain(timeout=2.0)
    assert service.in_flight_count == 0


@pytest.mark.asyncio
async def test_drain_cancels_pending_when_timeout_expires() -> None:
    class _SlowGraph:
        async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
            await asyncio.sleep(60)  # would block past the drain timeout
            return {}

    service = OrchestrationService(
        database=_DummyDatabase(),  # type: ignore[arg-type]
        event_emitter=_DummyEmitter(),  # type: ignore[arg-type]
        graphs={"investigation": _SlowGraph()},
    )
    await service.run_workflow(
        workflow_name="investigation",
        inputs={},
        background=True,
    )
    assert service.in_flight_count == 1
    await service.drain(timeout=0.1)
    # Drain cancels the task; the done_callback removes it from _tasks.
    # Give the loop one tick to process the cancellation cleanup.
    await asyncio.sleep(0.05)
    assert service.in_flight_count == 0
