"""Phase 7 WP3 — install_slow_query_logger is idempotent.

SQLAlchemy ``event.listens_for`` registers globally with no
dedup. Without the WP3 sentinel guard, calling
``install_slow_query_logger`` twice would attach two listener pairs and
every query would log twice.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event

from core.database.slow_query_log import (
    _INSTALLED_ATTR,
    install_slow_query_logger,
)


def _count_listeners(engine) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    target = engine.sync_engine if hasattr(engine, "sync_engine") else engine
    before = event.contains(target, "before_cursor_execute", lambda *_: None)
    # Use ``event.registry`` indirectly — easier to inspect via
    # ``_dispatch`` private attr, which is what the test relies on.
    dispatcher = target.dispatch.before_cursor_execute
    return len(dispatcher.listeners), len(target.dispatch.after_cursor_execute.listeners)


def test_install_attaches_listeners_once() -> None:
    engine = create_engine("sqlite://")
    before_b, before_a = _count_listeners(engine)

    install_slow_query_logger(engine, threshold_ms=100)
    after1_b, after1_a = _count_listeners(engine)
    assert after1_b == before_b + 1
    assert after1_a == before_a + 1
    assert getattr(engine, _INSTALLED_ATTR, False) is True

    install_slow_query_logger(engine, threshold_ms=100)
    after2_b, after2_a = _count_listeners(engine)
    # Second call MUST be a no-op.
    assert after2_b == after1_b
    assert after2_a == after1_a
