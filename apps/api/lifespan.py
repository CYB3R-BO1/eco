"""FastAPI lifespan — connect the data tier on startup, disconnect on shutdown.

Connection order is fastest-to-slowest (Postgres → Redis → Neo4j); shutdown is
the reverse. Failures during ``connect()`` propagate and prevent the app from
accepting traffic — that's deliberate: a half-up service that 500s every
request is worse than one that fails to start.

The :class:`GraphService` is constructed here (not via DI providers) so there's
a single instance per app — in later phases it'll cache the Cypher allowlist
and Relationship Matrix in-process.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from core.cache.redis import RedisClient
from core.config.settings import Settings, get_settings
from core.database.postgres import Database
from graph.graph_service.service import GraphService
from graph.neo4j.driver import Neo4jClient

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = getattr(app.state, "settings", None) or get_settings()

    db = Database(settings.postgres)
    redis_client = RedisClient(settings.redis)
    neo4j_client = Neo4jClient(settings.neo4j)

    log.info("lifespan.startup.begin", environment=settings.environment)

    await db.connect()
    await redis_client.connect()
    await neo4j_client.connect()

    graph_service = GraphService(neo4j_client)

    app.state.db = db
    app.state.redis = redis_client
    app.state.neo4j = neo4j_client
    app.state.graph_service = graph_service

    log.info("lifespan.startup.complete")

    try:
        yield
    finally:
        log.info("lifespan.shutdown.begin")
        await neo4j_client.disconnect()
        await redis_client.disconnect()
        await db.disconnect()
        log.info("lifespan.shutdown.complete")
