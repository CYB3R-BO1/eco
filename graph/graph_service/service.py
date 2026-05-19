"""Centralized graph mutation + traversal gateway.

PER ARCHITECTURAL INVARIANT (``CLAUDE.md`` §2): no module may issue writes
to Neo4j directly. This service is the ONLY surface that exposes graph
mutation; the underlying :class:`graph.neo4j.driver.Neo4jClient` is held
privately and never returned.

Phase 3 replaces the Phase 1 placeholder. The public surface is composed
of three role-specific helpers:

* :class:`graph.graph_service.mutations.GraphMutator` — node + relationship
  upserts. Schema-validated. Idempotent via MERGE.
* :class:`graph.graph_service.traversal.GraphTraverser` — bounded reads.
* :class:`graph.graph_service.integrity.IntegrityChecker` — DAG / orphan /
  confidence / provenance / stale-enrichment audit.

The historical ``run_read`` and ``run_write`` methods are removed. Callers
that need a one-off read must add a parameterized template to
:mod:`graph.queries`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from graph.graph_service.integrity import IntegrityChecker, IntegrityReport
from graph.graph_service.mutations import GraphMutator
from graph.graph_service.traversal import GraphTraverser, NodeNotFoundError
from graph.queries.mutations import PING_CYPHER

if TYPE_CHECKING:
    from core.events.emitter import EventEmitter
    from graph.governance.rejection_store import RejectionStore
    from graph.governance.validator import SchemaValidator
    from graph.neo4j.driver import Neo4jClient

log = structlog.get_logger(__name__)


class GraphService:
    """The single Neo4j gateway.

    Holds the validator, rejection store, and emitter so submodules can
    share them. Routes expose ``GraphService`` via FastAPI ``Depends``;
    consumers access ``.mutator``, ``.traverser``, ``.integrity`` as
    properties.
    """

    def __init__(
        self,
        client: "Neo4jClient",
        validator: "SchemaValidator",
        rejection_store: "RejectionStore",
        event_emitter: "EventEmitter",
    ) -> None:
        self._client = client
        self._validator = validator
        self._rejections = rejection_store
        self._events = event_emitter
        self._mutator = GraphMutator(client, validator, rejection_store, event_emitter)
        self._traverser = GraphTraverser(client, validator)
        self._integrity = IntegrityChecker(client)

    @property
    def mutator(self) -> GraphMutator:
        return self._mutator

    @property
    def traverser(self) -> GraphTraverser:
        return self._traverser

    @property
    def integrity(self) -> IntegrityChecker:
        return self._integrity

    async def ping(self) -> bool:
        """Trivial round-trip to prove the graph is reachable. Used by
        ``/ready`` healthcheck and by tests. Stays inside this class so the
        raw driver remains hidden from callers."""
        async with self._client.driver.session(database=self._client.database) as session:
            result = await session.run(PING_CYPHER)
            record = await result.single()
        return bool(record and record["ok"] == 1)


__all__ = [
    "GraphService",
    "IntegrityReport",
    "NodeNotFoundError",
]
