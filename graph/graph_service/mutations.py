"""Centralized graph mutation operations.

Every method on :class:`GraphMutator` does three things in this order:

1. **Validate** via :class:`graph.governance.SchemaValidator`.
2. **Persist a rejection** (Postgres ``graph_rejections`` row + audit event)
   if validation failed, then raise / return rejected.
3. **MERGE** the node or relationship in Neo4j with a fingerprint that
   makes the write idempotent.

The public surface is intentionally small: one method per node type, one
``create_relationship``, one ``batch`` helper. There is no ``run_write``
escape hatch — that's invariant #2 from CLAUDE.md made syntactic.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.events.emitter import EventEmitter
from core.events.types import EventType
from graph.governance.cardinality import MAX_RELATIONSHIPS_PER_NODE
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType
from graph.governance.rejection_store import RejectedMutation, RejectionStore
from graph.governance.validator import SchemaValidator, ValidationResult
from graph.neo4j.driver import Neo4jClient
from graph.queries.mutations import (
    create_relationship_cypher,
    upsert_node_cypher_no_apoc,
)
from graph.queries.traversal import COUNT_OUT_RELS_BY_TYPE

log = structlog.get_logger(__name__)


class GraphCardinalityError(ValueError):
    """A source node already has ``MAX_RELATIONSHIPS_PER_NODE`` outgoing
    edges of the requested relationship type.

    Distinct from a schema violation: the edge is *allowed*, just refused
    by the cardinality cap. Mapped to 409 at the API boundary.
    """

    def __init__(
        self, source_id: uuid.UUID, rel_type: RelationshipType, count: int
    ) -> None:
        super().__init__(
            f"cardinality limit reached on node {source_id} for "
            f"{rel_type.value}: {count} >= {MAX_RELATIONSHIPS_PER_NODE}"
        )
        self.source_id = source_id
        self.rel_type = rel_type
        self.count = count


@dataclass(frozen=True)
class MutationResult:
    """Returned by every mutation. ``was_new`` distinguishes initial create
    from idempotent replay; callers use it to decide whether to emit a
    ``GRAPH_NODE_CREATED`` / ``GRAPH_RELATIONSHIP_CREATED`` event."""

    id: uuid.UUID | str
    was_new: bool


def _relationship_fingerprint(
    source_id: uuid.UUID, rel: RelationshipType, target_id: uuid.UUID
) -> str:
    """Stable fingerprint for relationship MERGE.

    SHA-1 is fine — this isn't a security hash, just a deduplication key.
    """
    raw = f"{source_id}|{rel.value}|{target_id}".encode("ascii")
    return hashlib.sha1(raw).hexdigest()


class GraphMutator:
    """The only writer to Neo4j.

    Holds long-lived references to the Neo4j client, the SchemaValidator,
    and the RejectionStore. The session passed to each method is the
    *Postgres* session used to write the rejection record (Neo4j has its
    own session lifecycle).
    """

    def __init__(
        self,
        client: Neo4jClient,
        validator: SchemaValidator,
        rejection_store: RejectionStore,
        event_emitter: EventEmitter,
    ) -> None:
        self._client = client
        self._validator = validator
        self._rejections = rejection_store
        self._events = event_emitter

    # ------------------------------------------------------------------
    # Node upserts. One method per kind so the call site declares intent.
    # ------------------------------------------------------------------

    async def upsert_node(
        self,
        pg_session: AsyncSession,
        label: NodeType,
        node_id: uuid.UUID,
        properties: dict[str, Any],
        *,
        investigation_id: uuid.UUID | None = None,
    ) -> MutationResult:
        """Generic node upsert. Most callers should prefer the typed
        helpers below — :meth:`upsert_entity_node`,
        :meth:`upsert_investigation_node`, :meth:`upsert_evidence_node` —
        which fill in the standard property shape.
        """
        ts = datetime.now(timezone.utc)
        props = dict(properties)
        props.setdefault("confidence", 1.0)
        non_confidence_props = {k: v for k, v in props.items() if k != "confidence"}
        # Make sure id is always present
        props["id"] = str(node_id)
        non_confidence_props["id"] = str(node_id)

        cypher = upsert_node_cypher_no_apoc(label)
        async with self._client.driver.session(database=self._client.database) as session:
            result = await session.run(
                cypher,
                id=str(node_id),
                timestamp=ts.isoformat(),
                props=props,
                non_confidence_props=non_confidence_props,
            )
            record = await result.single()

        was_new = bool(record["was_new"]) if record else False

        if was_new:
            await self._events.emit(
                pg_session,
                EventType.GRAPH_NODE_CREATED,
                source="graph_service",
                investigation_id=investigation_id,
                target=f"{label.value}:{node_id}",
                metadata={
                    "label": label.value,
                    "node_id": str(node_id),
                    "confidence": props.get("confidence"),
                },
                confidence=float(props.get("confidence", 1.0)),
            )
            log.info(
                "graph.node.created",
                label=label.value,
                node_id=str(node_id),
                investigation_id=str(investigation_id) if investigation_id else None,
            )
        return MutationResult(id=node_id, was_new=was_new)

    async def upsert_entity_node(
        self,
        pg_session: AsyncSession,
        label: NodeType,
        entity_id: uuid.UUID,
        canonical_form: str,
        *,
        confidence: float,
        investigation_id: uuid.UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> MutationResult:
        """Upsert a node representing a resolved IOC entity (IP, Domain,
        URL, Hash, Email).

        Property shape comes from the ``entity_aliases`` table: every
        entity node carries ``canonical_form``, ``entity_type`` (the
        Phase 2 EntityType value), and ``confidence``.
        """
        props: dict[str, Any] = {
            "canonical_form": canonical_form,
            "confidence": float(confidence),
        }
        if extra:
            props.update(extra)
        return await self.upsert_node(
            pg_session,
            label,
            entity_id,
            props,
            investigation_id=investigation_id,
        )

    async def upsert_investigation_node(
        self,
        pg_session: AsyncSession,
        investigation_id: uuid.UUID,
        title: str,
        status: str,
        severity: str,
        confidence: float,
    ) -> MutationResult:
        return await self.upsert_node(
            pg_session,
            NodeType.INVESTIGATION,
            investigation_id,
            {
                "title": title,
                "status": status,
                "severity": severity,
                "confidence": float(confidence),
            },
            investigation_id=investigation_id,
        )

    async def upsert_evidence_node(
        self,
        pg_session: AsyncSession,
        evidence_id: uuid.UUID,
        source: str,
        type_: str,
        provenance_level: str,
        confidence: float,
        chain_of_custody: list[uuid.UUID],
        created_at: datetime,
        *,
        investigation_id: uuid.UUID | None = None,
    ) -> MutationResult:
        props = {
            "source": source,
            "type": type_,
            "provenance_level": provenance_level,
            "confidence": float(confidence),
            "chain_of_custody": [str(x) for x in chain_of_custody],
            "created_at": created_at.isoformat(),
        }
        return await self.upsert_node(
            pg_session,
            NodeType.EVIDENCE,
            evidence_id,
            props,
            investigation_id=investigation_id,
        )

    # ------------------------------------------------------------------
    # Relationship creation. Always validated first; rejections persisted.
    # ------------------------------------------------------------------

    async def create_relationship(
        self,
        pg_session: AsyncSession,
        source_type: NodeType,
        source_id: uuid.UUID,
        rel: RelationshipType,
        target_type: NodeType,
        target_id: uuid.UUID,
        *,
        confidence: float,
        evidence_id: uuid.UUID | None = None,
        investigation_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MutationResult | None:
        """Validate, check cardinality, then MERGE.

        Returns ``None`` on rejection (which has been recorded). Returns a
        :class:`MutationResult` on success. Raising would force every
        caller to wrap in try/except; for the bulk-correlation case we
        want the loop to continue past rejected edges.
        """
        # 1) Schema validation
        validation: ValidationResult = self._validator.validate_edge(
            source_type, rel, target_type
        )
        if not validation.ok:
            await self._rejections.record(
                pg_session,
                RejectedMutation(
                    source_type=source_type,
                    source_id=source_id,
                    relationship_type=rel,
                    target_type=target_type,
                    target_id=target_id,
                    reason=validation.reason or "schema rejected",
                    investigation_id=investigation_id,
                    attempt_metadata=metadata or {},
                ),
            )
            return None

        # 2) Cardinality check (per-type degree cap)
        async with self._client.driver.session(database=self._client.database) as session:
            count_result = await session.run(
                COUNT_OUT_RELS_BY_TYPE, node_id=str(source_id)
            )
            counts = {r["rel_type"]: r["cnt"] async for r in count_result}
        if counts.get(rel.value, 0) >= MAX_RELATIONSHIPS_PER_NODE:
            reason = (
                f"cardinality limit {MAX_RELATIONSHIPS_PER_NODE} reached on "
                f"({source_type.value}:{source_id}) for {rel.value}"
            )
            await self._rejections.record(
                pg_session,
                RejectedMutation(
                    source_type=source_type,
                    source_id=source_id,
                    relationship_type=rel,
                    target_type=target_type,
                    target_id=target_id,
                    reason=reason,
                    investigation_id=investigation_id,
                    attempt_metadata={
                        "current_count": counts.get(rel.value, 0),
                        "limit": MAX_RELATIONSHIPS_PER_NODE,
                    },
                ),
            )
            raise GraphCardinalityError(
                source_id, rel, counts.get(rel.value, 0)
            )

        # 3) MERGE
        fingerprint = _relationship_fingerprint(source_id, rel, target_id)
        ts = datetime.now(timezone.utc)
        async with self._client.driver.session(database=self._client.database) as session:
            result = await session.run(
                create_relationship_cypher(rel),
                source_id=str(source_id),
                target_id=str(target_id),
                fingerprint=fingerprint,
                timestamp=ts.isoformat(),
                confidence=float(confidence),
                evidence_id=str(evidence_id) if evidence_id else None,
                investigation_id=str(investigation_id) if investigation_id else None,
                metadata=metadata or {},
            )
            record = await result.single()

        was_new = bool(record["was_new"]) if record else False

        if was_new:
            await self._events.emit(
                pg_session,
                EventType.GRAPH_RELATIONSHIP_CREATED,
                source="graph_service",
                investigation_id=investigation_id,
                target=(
                    f"({source_type.value}:{source_id})-"
                    f"[{rel.value}]->({target_type.value}:{target_id})"
                ),
                evidence_refs=[evidence_id] if evidence_id else None,
                metadata={
                    "source_type": source_type.value,
                    "source_id": str(source_id),
                    "relationship_type": rel.value,
                    "target_type": target_type.value,
                    "target_id": str(target_id),
                    "fingerprint": fingerprint,
                },
                confidence=float(confidence),
            )
            log.info(
                "graph.relationship.created",
                source=f"{source_type.value}:{source_id}",
                rel=rel.value,
                target=f"{target_type.value}:{target_id}",
                investigation_id=str(investigation_id) if investigation_id else None,
            )
        return MutationResult(id=fingerprint, was_new=was_new)
