"""Graph read endpoints.

All three endpoints go through :class:`GraphService` — never the raw
Neo4j driver. Write endpoints don't exist on the public API: graph
mutations only happen as a side effect of ingestion (CORRELATING phase),
which keeps the rule "graph writes pass through Entity Resolution and
Schema Governance" syntactically true on the HTTP surface as well.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from apps.api.dependencies import GraphServiceDep
from schemas.api.graph import (
    EdgeResponse,
    GraphQueryRequest,
    GraphSliceResponse,
    IntegrityReportResponse,
    NodeResponse,
    NodeWithNeighborsResponse,
)

router = APIRouter(prefix="/graph", tags=["graph"])


def _node_to_response(n) -> NodeResponse:
    return NodeResponse(id=n.id, labels=n.labels, properties=n.properties)


def _edge_to_response(e) -> EdgeResponse:
    return EdgeResponse(
        source_id=e.source_id,
        target_id=e.target_id,
        type=e.type,
        properties=e.properties,
    )


@router.post(
    "/query",
    response_model=GraphSliceResponse,
    summary="Bounded graph traversal from a starting node",
)
async def query_graph(
    request: GraphQueryRequest,
    graph: GraphServiceDep,
) -> GraphSliceResponse:
    slice_ = await graph.traverser.query(
        request.start_node_id,
        depth=request.depth,
        rel_types=request.rel_types or None,
        min_confidence=request.min_confidence,
        limit=request.limit,
    )
    return GraphSliceResponse(
        nodes=[_node_to_response(n) for n in slice_.nodes],
        edges=[_edge_to_response(e) for e in slice_.edges],
    )


@router.get(
    "/investigation/{investigation_id}",
    response_model=GraphSliceResponse,
    summary="Full subgraph anchored at an investigation",
)
async def get_investigation_subgraph(
    investigation_id: uuid.UUID,
    graph: GraphServiceDep,
) -> GraphSliceResponse:
    slice_ = await graph.traverser.investigation(investigation_id)
    return GraphSliceResponse(
        nodes=[_node_to_response(n) for n in slice_.nodes],
        edges=[_edge_to_response(e) for e in slice_.edges],
    )


@router.get(
    "/node/{node_id}",
    response_model=NodeWithNeighborsResponse,
    summary="A node plus its one-hop incoming and outgoing edges",
)
async def get_node(
    node_id: uuid.UUID,
    graph: GraphServiceDep,
) -> NodeWithNeighborsResponse:
    node, incoming, outgoing = await graph.traverser.node_with_neighbors(node_id)
    return NodeWithNeighborsResponse(
        node=_node_to_response(node),
        incoming=[_edge_to_response(e) for e in incoming],
        outgoing=[_edge_to_response(e) for e in outgoing],
    )


@router.get(
    "/integrity/{investigation_id}",
    response_model=IntegrityReportResponse,
    summary="On-demand integrity verification for an investigation",
)
async def get_integrity_report(
    investigation_id: uuid.UUID,
    graph: GraphServiceDep,
) -> IntegrityReportResponse:
    report = await graph.integrity.check(investigation_id)
    return IntegrityReportResponse(**report.to_dict())
