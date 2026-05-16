"""FastAPI dependency providers.

Long-lived components (``Database``, ``RedisClient``, ``Neo4jClient``,
``GraphService``) are constructed in the lifespan and parked on ``app.state``;
these providers expose them via FastAPI's ``Depends`` system so routes stay
testable. Prefer the ``*Dep`` ``Annotated`` aliases in route signatures.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache.redis import RedisClient
from core.config.settings import Settings, get_settings
from core.database.postgres import Database
from graph.graph_service.service import GraphService
from graph.neo4j.driver import Neo4jClient


def get_settings_dep() -> Settings:
    return get_settings()


def get_database(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


def get_redis_client(request: Request) -> RedisClient:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_neo4j_client(request: Request) -> Neo4jClient:
    return request.app.state.neo4j  # type: ignore[no-any-return]


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service  # type: ignore[no-any-return]


async def get_db_session(
    db: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with db.session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[RedisClient, Depends(get_redis_client)]
Neo4jDep = Annotated[Neo4jClient, Depends(get_neo4j_client)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
