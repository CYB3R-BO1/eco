"""Async Neo4j driver wrapper.

``verify_connectivity()`` runs on :meth:`connect` so the app fails fast at
startup if the graph isn't reachable — much better than discovering the
misconfiguration on the first user request.

**Architectural invariant** (``CLAUDE.md`` §2): the raw driver should only be
accessed via :class:`graph.graph_service.GraphService`. Direct callers in
business code are an invariant violation and will be removed in code review.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase

if TYPE_CHECKING:
    from core.config.settings import Neo4jSettings

log = structlog.get_logger(__name__)


class Neo4jClient:
    def __init__(self, settings: Neo4jSettings) -> None:
        self._settings = settings
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            self._settings.uri,
            auth=(self._settings.user, self._settings.password.get_secret_value()),
            max_connection_pool_size=self._settings.max_connection_pool_size,
        )
        await self._driver.verify_connectivity()
        log.info("neo4j.connected", uri=self._settings.uri, database=self._settings.database)

    async def disconnect(self) -> None:
        if self._driver is None:
            return
        await self._driver.close()
        self._driver = None
        log.info("neo4j.disconnected")

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4j is not connected")
        return self._driver

    @property
    def database(self) -> str:
        return self._settings.database

    async def healthcheck(self) -> bool:
        if self._driver is None:
            return False
        try:
            await self._driver.verify_connectivity()
        except Exception:
            log.exception("neo4j.healthcheck_failed")
            return False
        return True
