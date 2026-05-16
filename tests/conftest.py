"""Pytest fixtures.

These tests use ``httpx.ASGITransport`` which does NOT trigger the FastAPI
lifespan. That's deliberate: tests in ``tests/unit/`` cover routes that don't
need Postgres/Redis/Neo4j (just ``/health`` and ``/live``). Routes that touch
``app.state.db`` / ``redis`` / ``neo4j`` belong in ``tests/integration/`` where
docker-compose-backed runs spin up the real data tier.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
