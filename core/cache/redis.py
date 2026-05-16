"""Async Redis client wrapper.

``decode_responses=False`` keeps the client binary-safe — later phases push
msgpack/orjson-encoded payloads into queues and shouldn't fight the codec.
Explicit ``connect``/``disconnect`` lets the FastAPI lifespan control when the
connection pool exists, matching the pattern used by :class:`Database` and
:class:`graph.neo4j.driver.Neo4jClient`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from redis.asyncio import ConnectionPool, Redis

if TYPE_CHECKING:
    from core.config.settings import RedisSettings

log = structlog.get_logger(__name__)


class RedisClient:
    def __init__(self, settings: RedisSettings) -> None:
        self._settings = settings
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._pool = ConnectionPool.from_url(
            self._settings.url,
            max_connections=self._settings.max_connections,
            decode_responses=False,
        )
        self._client = Redis(connection_pool=self._pool)
        log.info("redis.connected", host=self._settings.host, db=self._settings.db)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
        log.info("redis.disconnected")

    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Redis is not connected")
        return self._client

    async def healthcheck(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            log.exception("redis.healthcheck_failed")
            return False
