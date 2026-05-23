"""Phase 7 WP4 — Database.engine accessor contract.

The accessor returns the engine post-connect and raises pre-connect.
Avoids private-attr access (``db._engine``) at call sites.
"""
from __future__ import annotations

import pytest

from core.config.settings import PostgresSettings
from core.database.postgres import Database


def test_engine_raises_before_connect() -> None:
    db = Database(PostgresSettings())
    with pytest.raises(RuntimeError, match="not connected"):
        _ = db.engine


@pytest.mark.asyncio
async def test_engine_returns_after_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``create_async_engine`` so we don't need a real DB.

    The point of the test is the accessor contract, not the engine
    itself. We patch the factory to return a sentinel and assert the
    accessor returns it.
    """
    db = Database(PostgresSettings())

    sentinel = object()

    def _fake_create_async_engine(*args: object, **kwargs: object) -> object:
        return sentinel

    import core.database.postgres as mod

    monkeypatch.setattr(mod, "create_async_engine", _fake_create_async_engine)
    # async_sessionmaker also gets called — give it a no-op so connect()
    # completes without raising.
    monkeypatch.setattr(mod, "async_sessionmaker", lambda *a, **kw: lambda: None)

    await db.connect()
    assert db.engine is sentinel
