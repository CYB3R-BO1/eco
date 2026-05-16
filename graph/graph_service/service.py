"""Centralized graph mutation gateway.

PER ARCHITECTURAL INVARIANT (``CLAUDE.md`` §2): no module may issue writes to
Neo4j directly. Every mutation must pass through this service. Phase 1 only
provides connection routing — the validation layer arrives in later phases.

LATER PHASES MUST ADD HERE:

* schema validation against a Cypher allowlist
* enforcement of the Relationship Matrix (``PLAN.md`` §6)
* entity-resolution lookup before node creation
* required ``evidence_id`` reference on every mutation
* required ``confidence`` property on every relationship
* timestamp consistency on every write
* audit-event emission for every successful mutation
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from neo4j import AsyncManagedTransaction

    from graph.neo4j.driver import Neo4jClient

log = structlog.get_logger(__name__)


class GraphService:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def run_read(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        async with self._client.driver.session(database=self._client.database) as session:
            result = await session.run(cypher, **params)
            return [record.data() async for record in result]

    async def run_write(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        """Phase 1 placeholder.

        In later phases this routes through Entity Resolution and schema
        validation before issuing the write. Callers must not bypass this
        method by accessing ``self._client.driver`` directly.
        """
        async with self._client.driver.session(database=self._client.database) as session:
            return await session.execute_write(self._tx_run, cypher, params)

    @staticmethod
    async def _tx_run(
        tx: AsyncManagedTransaction,
        cypher: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        result = await tx.run(cypher, **params)
        return [record.data() async for record in result]
