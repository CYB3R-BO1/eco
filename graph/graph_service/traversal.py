"""Read-side graph queries with mandatory bounds.

Every method here goes through :meth:`SchemaValidator.validate_traversal_depth`
and applies a hard ``limit`` cap. There is no raw Cypher entry point — even
:meth:`run_read_bounded` requires a parameterized template name, not a free
string, so analysts cannot smuggle a 50-hop traversal in via the API.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from neo4j import Record

from graph.governance.cardinality import (
    MAX_QUERY_LIMIT,
    MAX_TRAVERSAL_DEPTH,
    QUERY_TIMEOUT_SECONDS,
)
from graph.governance.relationship_types import RelationshipType
from graph.governance.validator import SchemaValidator
from graph.neo4j.driver import Neo4jClient
from graph.queries.traversal import (
    dsl_query,
    investigation_subgraph,
    node_neighborhood,
    node_with_neighbors,
    render_rel_filter,
)

log = structlog.get_logger(__name__)


class NodeNotFoundError(LookupError):
    def __init__(self, node_id: uuid.UUID) -> None:
        super().__init__(f"node not found: {node_id}")
        self.node_id = node_id


@dataclass(frozen=True)
class GraphNode:
    id: str
    labels: list[str]
    properties: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    type: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class GraphSlice:
    """A subgraph result: deduplicated nodes + edges."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphTraverser:
    def __init__(self, client: Neo4jClient, validator: SchemaValidator) -> None:
        self._client = client
        self._validator = validator

    async def neighborhood(
        self,
        node_id: uuid.UUID,
        *,
        depth: int = 1,
        limit: int = 100,
    ) -> GraphSlice:
        self._validator.validate_traversal_depth(depth)
        limit = _clamp_limit(limit)
        async with self._client.driver.session(database=self._client.database) as session:
            try:
                result = await asyncio.wait_for(
                    session.run(
                        node_neighborhood(depth),
                        node_id=str(node_id),
                        limit=limit,
                    ),
                    timeout=QUERY_TIMEOUT_SECONDS,
                )
                records = [record async for record in result]
            except asyncio.TimeoutError:
                log.warning(
                    "graph.traversal.timeout",
                    node_id=str(node_id),
                    depth=depth,
                    limit=limit,
                )
                raise
        if not records:
            raise NodeNotFoundError(node_id)
        return _flatten_path_records(records)

    async def investigation(self, investigation_id: uuid.UUID) -> GraphSlice:
        async with self._client.driver.session(database=self._client.database) as session:
            result = await asyncio.wait_for(
                session.run(
                    investigation_subgraph(),
                    investigation_id=str(investigation_id),
                ),
                timeout=QUERY_TIMEOUT_SECONDS,
            )
            record = await result.single()
        if record is None or record["investigation"] is None:
            raise NodeNotFoundError(investigation_id)
        nodes_raw = [record["investigation"]] + list(record["members"] or [])
        rels_raw = list(record["rels"] or [])
        nodes = _dedupe_nodes([_node_from(n) for n in nodes_raw if n is not None])
        edges = _dedupe_edges([_edge_from(r) for r in rels_raw if r is not None])
        return GraphSlice(nodes=nodes, edges=edges)

    async def node_with_neighbors(
        self, node_id: uuid.UUID
    ) -> tuple[GraphNode, list[GraphEdge], list[GraphEdge]]:
        """One-hop view used by GET /graph/node/{id}: return node + its
        incoming and outgoing edges separately."""
        async with self._client.driver.session(database=self._client.database) as session:
            result = await asyncio.wait_for(
                session.run(
                    node_with_neighbors(),
                    node_id=str(node_id),
                ),
                timeout=QUERY_TIMEOUT_SECONDS,
            )
            record = await result.single()
        if record is None or record["node"] is None:
            raise NodeNotFoundError(node_id)
        node = _node_from(record["node"])
        out_edges = [
            _edge_from(entry["edge"])
            for entry in (record["outgoing"] or [])
            if entry and entry.get("edge") is not None
        ]
        in_edges = [
            _edge_from(entry["edge"])
            for entry in (record["incoming"] or [])
            if entry and entry.get("edge") is not None
        ]
        return node, in_edges, out_edges

    async def query(
        self,
        start_node_id: uuid.UUID,
        *,
        depth: int,
        rel_types: list[RelationshipType] | None,
        min_confidence: float,
        limit: int,
    ) -> GraphSlice:
        self._validator.validate_traversal_depth(depth)
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        limit = _clamp_limit(limit)
        rel_clause = render_rel_filter([r.value for r in (rel_types or [])])
        cypher = dsl_query(depth, rel_clause)
        async with self._client.driver.session(database=self._client.database) as session:
            result = await asyncio.wait_for(
                session.run(
                    cypher,
                    start_node_id=str(start_node_id),
                    min_confidence=float(min_confidence),
                    limit=limit,
                ),
                timeout=QUERY_TIMEOUT_SECONDS,
            )
            records = [record async for record in result]
        if not records:
            raise NodeNotFoundError(start_node_id)
        return _flatten_path_records(records)


def _clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_QUERY_LIMIT)


def _node_from(raw: Any) -> GraphNode:
    labels = sorted(raw.labels) if hasattr(raw, "labels") else []
    props = dict(raw) if raw is not None else {}
    return GraphNode(
        id=str(props.get("id", "")),
        labels=list(labels),
        properties=props,
    )


def _edge_from(raw: Any) -> GraphEdge:
    if raw is None:
        return GraphEdge(source_id="", target_id="", type="", properties={})
    return GraphEdge(
        source_id=str(getattr(raw, "start_node", {}).get("id", ""))
        if hasattr(raw, "start_node")
        else "",
        target_id=str(getattr(raw, "end_node", {}).get("id", ""))
        if hasattr(raw, "end_node")
        else "",
        type=raw.type if hasattr(raw, "type") else "",
        properties=dict(raw) if raw is not None else {},
    )


def _flatten_path_records(records: list[Record]) -> GraphSlice:
    """Collapse a list of path-shaped records into deduped node / edge lists.

    Path records come back as {start, nodes, rels}; the same node or edge
    may appear in many paths, so we dedupe by id / fingerprint.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_node_ids: set[str] = set()
    seen_edge_fps: set[str] = set()
    for rec in records:
        for n in rec.get("nodes", []) or []:
            if n is None:
                continue
            node = _node_from(n)
            if node.id and node.id not in seen_node_ids:
                nodes.append(node)
                seen_node_ids.add(node.id)
        # include the anchor node
        anchor = rec.get("start")
        if anchor is not None:
            anchor_node = _node_from(anchor)
            if anchor_node.id and anchor_node.id not in seen_node_ids:
                nodes.append(anchor_node)
                seen_node_ids.add(anchor_node.id)
        for r in rec.get("rels", []) or []:
            if r is None:
                continue
            edge = _edge_from(r)
            fp = edge.properties.get("fingerprint")
            key = (
                str(fp)
                if fp
                else f"{edge.source_id}|{edge.type}|{edge.target_id}"
            )
            if key not in seen_edge_fps:
                edges.append(edge)
                seen_edge_fps.add(key)
    return GraphSlice(nodes=_dedupe_nodes(nodes), edges=_dedupe_edges(edges))


def _dedupe_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    seen: set[str] = set()
    out: list[GraphNode] = []
    for n in nodes:
        if n.id and n.id not in seen:
            out.append(n)
            seen.add(n.id)
    return out


def _dedupe_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    seen: set[str] = set()
    out: list[GraphEdge] = []
    for e in edges:
        fp = e.properties.get("fingerprint")
        key = str(fp) if fp else f"{e.source_id}|{e.type}|{e.target_id}"
        if key not in seen:
            out.append(e)
            seen.add(key)
    return out


__all__ = [
    "GraphTraverser",
    "GraphNode",
    "GraphEdge",
    "GraphSlice",
    "NodeNotFoundError",
    "MAX_TRAVERSAL_DEPTH",
]
