"""GraphCorrelator — CORRELATING-phase orchestrator.

Given an investigation that just finished ENRICHING, walk its Evidence and
the entities each Evidence references, then materialize the matching
nodes and edges in Neo4j through :class:`GraphService`. The architectural
gates (schema validation, rejection persistence, idempotent MERGE) live
inside the service; the correlator is purely an iterator over Postgres
state that issues typed mutation calls.

Idempotent by construction: every node is upserted on ``id`` and every
relationship is MERGEd on a deterministic fingerprint. Running the
correlator a second time on the same investigation produces zero new
nodes and zero new edges (only updated ``updated_at`` timestamps), which
is the property the replay test asserts.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select

from core.confidence.propagate import derived_confidence
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.events.types import EventType
from evidence.provenance import reliability_for
from graph.governance.node_types import NodeType, from_entity_type
from graph.governance.relationship_types import RelationshipType
from graph.graph_service.service import GraphService
from resolution.types import EntityType
from storage.postgres.models.entity_alias import EntityAlias
from storage.postgres.models.evidence import EvidenceRow
from storage.postgres.models.investigation import Investigation

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CorrelationStats:
    nodes_created: int
    edges_created: int
    edges_rejected: int
    evidence_processed: int
    entities_processed: int


class GraphCorrelator:
    def __init__(
        self,
        database: Database,
        graph_service: GraphService,
        event_emitter: EventEmitter,
    ) -> None:
        self._db = database
        self._graph = graph_service
        self._events = event_emitter

    async def correlate(self, investigation_id: uuid.UUID) -> CorrelationStats:
        """Materialize the investigation's deterministic state in Neo4j.

        One Postgres session lives for the duration so that the audit
        events (and any rejection rows) commit atomically at the end.
        """
        nodes_created = 0
        edges_created = 0
        edges_rejected = 0
        evidence_processed = 0
        entities_processed = 0

        async with self._db.session() as pg_session:
            # 1) Investigation node
            inv = await pg_session.get(Investigation, investigation_id)
            if inv is None:
                raise LookupError(f"investigation not found: {investigation_id}")

            inv_result = await self._graph.mutator.upsert_investigation_node(
                pg_session,
                investigation_id=inv.id,
                title=inv.title,
                status=inv.status.value,
                severity=inv.severity,
                confidence=inv.confidence_score or 1.0,
            )
            if inv_result.was_new:
                nodes_created += 1

            # 2) Evidence rows for this investigation
            ev_stmt = (
                select(EvidenceRow)
                .where(EvidenceRow.investigation_id == investigation_id)
                .order_by(EvidenceRow.created_at.asc())
            )
            evidences = (await pg_session.execute(ev_stmt)).scalars().all()

            # Cache of entity_id -> NodeType so we don't re-fetch alias rows.
            entity_node_cache: dict[uuid.UUID, NodeType] = {}

            for ev in evidences:
                ev_result = await self._graph.mutator.upsert_evidence_node(
                    pg_session,
                    evidence_id=ev.id,
                    source=ev.source,
                    type_=ev.type,
                    provenance_level=ev.provenance.get("level", "USER_SUPPLIED"),
                    confidence=ev.confidence,
                    chain_of_custody=[
                        uuid.UUID(x) if isinstance(x, str) else x
                        for x in ev.provenance.get("chain_of_custody", [])
                    ],
                    created_at=ev.created_at,
                    investigation_id=investigation_id,
                )
                if ev_result.was_new:
                    nodes_created += 1
                evidence_processed += 1

                # Evidence -[:PART_OF]-> Investigation
                part_of_conf = derived_confidence(
                    ev.confidence,
                    float(ev.provenance.get("source_reliability", reliability_for(ev.source))),
                )
                edge_res = await self._graph.mutator.create_relationship(
                    pg_session,
                    NodeType.EVIDENCE,
                    ev.id,
                    RelationshipType.PART_OF,
                    NodeType.INVESTIGATION,
                    investigation_id,
                    confidence=part_of_conf,
                    evidence_id=ev.id,
                    investigation_id=investigation_id,
                    metadata={"source": ev.source},
                )
                if edge_res is None:
                    edges_rejected += 1
                elif edge_res.was_new:
                    edges_created += 1

                # For each linked entity, materialize the entity node and
                # the Evidence -[:RELATED_TO]-> Entity + Entity -[:PART_OF]-> Investigation edges.
                for entity_id in ev.linked_entities or []:
                    node_label = entity_node_cache.get(entity_id)
                    if node_label is None:
                        alias = await pg_session.get(EntityAlias, entity_id)
                        if alias is None:
                            log.warning(
                                "correlator.missing_entity",
                                evidence_id=str(ev.id),
                                entity_id=str(entity_id),
                            )
                            continue
                        node_label = from_entity_type(alias.entity_type)
                        if node_label is None:
                            # Non-graphable type (raw_log, json_payload, cve)
                            entity_node_cache[entity_id] = NodeType.EVIDENCE  # sentinel
                            continue
                        entity_node_cache[entity_id] = node_label
                        ent_res = await self._graph.mutator.upsert_entity_node(
                            pg_session,
                            label=node_label,
                            entity_id=entity_id,
                            canonical_form=alias.canonical_form,
                            confidence=alias.confidence,
                            investigation_id=investigation_id,
                            extra={"entity_type": alias.entity_type.value},
                        )
                        if ent_res.was_new:
                            nodes_created += 1
                        entities_processed += 1

                        # Entity -[:PART_OF]-> Investigation
                        entity_part_conf = derived_confidence(
                            alias.confidence, part_of_conf
                        )
                        edge_res2 = await self._graph.mutator.create_relationship(
                            pg_session,
                            node_label,
                            entity_id,
                            RelationshipType.PART_OF,
                            NodeType.INVESTIGATION,
                            investigation_id,
                            confidence=entity_part_conf,
                            evidence_id=ev.id,
                            investigation_id=investigation_id,
                        )
                        if edge_res2 is None:
                            edges_rejected += 1
                        elif edge_res2.was_new:
                            edges_created += 1

                        # URLs additionally hang off their parent Domain.
                        if alias.entity_type is EntityType.URL:
                            await self._link_url_to_parent_domain(
                                pg_session,
                                investigation_id=investigation_id,
                                url_entity_id=entity_id,
                                evidence_id=ev.id,
                                evidence_confidence=ev.confidence,
                            )

                    if node_label is NodeType.EVIDENCE:
                        # sentinel — skip, this entity is not graphable
                        continue

                    # Evidence -[:RELATED_TO]-> Entity
                    rel_conf = derived_confidence(ev.confidence, part_of_conf)
                    edge_res3 = await self._graph.mutator.create_relationship(
                        pg_session,
                        NodeType.EVIDENCE,
                        ev.id,
                        RelationshipType.RELATED_TO,
                        node_label,
                        entity_id,
                        confidence=rel_conf,
                        evidence_id=ev.id,
                        investigation_id=investigation_id,
                    )
                    if edge_res3 is None:
                        edges_rejected += 1
                    elif edge_res3.was_new:
                        edges_created += 1

            # Audit event summarizing the correlation.
            await self._events.emit(
                pg_session,
                EventType.CORRELATION_COMPLETED,
                source="graph_correlator",
                investigation_id=investigation_id,
                target=str(investigation_id),
                metadata={
                    "nodes_created": nodes_created,
                    "edges_created": edges_created,
                    "edges_rejected": edges_rejected,
                    "evidence_processed": evidence_processed,
                    "entities_processed": entities_processed,
                },
            )
            await pg_session.commit()

        stats = CorrelationStats(
            nodes_created=nodes_created,
            edges_created=edges_created,
            edges_rejected=edges_rejected,
            evidence_processed=evidence_processed,
            entities_processed=entities_processed,
        )
        log.info(
            "graph.correlation.completed",
            investigation_id=str(investigation_id),
            **stats.__dict__,
        )
        return stats

    async def _link_url_to_parent_domain(
        self,
        pg_session,
        *,
        investigation_id: uuid.UUID,
        url_entity_id: uuid.UUID,
        evidence_id: uuid.UUID,
        evidence_confidence: float,
    ) -> None:
        """If the URL alias has a parent domain alias variant, MERGE the
        URL -[:PART_OF]-> Domain edge.

        The parent domain entity was created (or referenced) by
        :class:`EntityResolutionService` during ingestion. We look it up
        here by canonical_form (extracting via urlparse-style splitting)
        and use the existing alias's id and confidence.
        """
        # Use the same parent_domain helper used by resolution.
        alias = await pg_session.get(EntityAlias, url_entity_id)
        if alias is None:
            return
        try:
            from resolution.normalization import parent_domain  # local import to avoid cycles
        except ImportError:
            return
        try:
            parent_form = parent_domain(alias.canonical_form)
        except ValueError:
            return
        if not parent_form:
            return
        stmt = select(EntityAlias).where(
            EntityAlias.canonical_form == parent_form,
            EntityAlias.entity_type == EntityType.DOMAIN,
        )
        parent_alias = (await pg_session.execute(stmt)).scalar_one_or_none()
        if parent_alias is None:
            return
        # The parent domain node may not yet be in the graph (e.g., if no
        # Evidence references it directly); ensure it before linking.
        parent_label = from_entity_type(parent_alias.entity_type)
        if parent_label is None:
            return
        await self._graph.mutator.upsert_entity_node(
            pg_session,
            label=parent_label,
            entity_id=parent_alias.id,
            canonical_form=parent_alias.canonical_form,
            confidence=parent_alias.confidence,
            investigation_id=investigation_id,
            extra={"entity_type": parent_alias.entity_type.value},
        )
        edge_conf = derived_confidence(
            evidence_confidence, alias.confidence, parent_alias.confidence
        )
        await self._graph.mutator.create_relationship(
            pg_session,
            NodeType.URL,
            url_entity_id,
            RelationshipType.PART_OF,
            NodeType.DOMAIN,
            parent_alias.id,
            confidence=edge_conf,
            evidence_id=evidence_id,
            investigation_id=investigation_id,
        )
