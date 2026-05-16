"""Async PostgreSQL engine + session lifecycle.

A single :class:`Database` instance is created in the FastAPI lifespan and
shared via ``app.state``. Sessions are short-lived and acquired per request
through ``SessionDep`` in ``apps/api/dependencies.py``.

Phase 1 owns no ORM models — those land under ``storage/postgres/models/`` in
Phase 2. This module is purely connection management.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from core.config.settings import PostgresSettings

log = structlog.get_logger(__name__)


class Database:
    """Owns the async engine and the session factory."""

    def __init__(self, settings: PostgresSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        if self._engine is not None:
            return
        self._engine = create_async_engine(
            self._settings.dsn,
            pool_size=self._settings.pool_size,
            max_overflow=self._settings.max_overflow,
            pool_pre_ping=True,
            echo=self._settings.echo,
        )
        self._sessionmaker = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        log.info("postgres.connected", host=self._settings.host, db=self._settings.db)

    async def disconnect(self) -> None:
        if self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None
        log.info("postgres.disconnected")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("Database is not connected")
        async with self._sessionmaker() as session:
            yield session

    async def healthcheck(self) -> bool:
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            log.exception("postgres.healthcheck_failed")
            return False
        return True
