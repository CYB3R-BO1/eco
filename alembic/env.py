"""Alembic migration runner (async).

Pulls the DSN from :func:`core.config.settings.get_settings` rather than from
``alembic.ini`` so there's a single source of truth for connection info.
Imports :class:`core.database.base.Base` to populate ``target_metadata``;
domain ORM modules live in ``storage.postgres.models`` and should be imported
below as they're added so autogenerate picks them up.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from core.config.settings import get_settings
from core.database.base import Base

# Phase 2+: uncomment as models are added so they appear in target_metadata.
# from storage.postgres.models import *  # noqa: F401, F403

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.postgres.dsn)


def run_migrations_offline() -> None:
    context.configure(
        url=_settings.postgres.dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _settings.postgres.dsn
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_migrations_online_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
