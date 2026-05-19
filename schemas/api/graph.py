"""Pydantic schemas for the Phase 3 graph endpoints.

The wire shape is deliberately small. ``GraphQueryRequest`` enforces the
depth / limit / confidence bounds at the validation layer so an
out-of-range request 422s before any Cypher runs.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from graph.governance.cardinality import MAX_QUERY_LIMIT, MAX_TRAVERSAL_DEPTH
from graph.governance.relationship_types import RelationshipType


class NodeResponse(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any] = Field(default_factory=dict)


class EdgeResponse(BaseModel):
    source_id: str
    target_id: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphSliceResponse(BaseModel):
    nodes: list[NodeResponse]
    edges: list[EdgeResponse]


class NodeWithNeighborsResponse(BaseModel):
    node: NodeResponse
    incoming: list[EdgeResponse]
    outgoing: list[EdgeResponse]


class GraphQueryRequest(BaseModel):
    """Structured DSL for the POST /api/v1/graph/query endpoint.

    No raw Cypher. ``rel_types`` is intersected with the actual edges in
    the graph; an empty list means "any allowed relationship type."
    """

    model_config = ConfigDict(extra="forbid")

    start_node_id: uuid.UUID
    depth: int = Field(default=2, ge=1, le=MAX_TRAVERSAL_DEPTH)
    rel_types: list[RelationshipType] = Field(default_factory=list)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=200, ge=1, le=MAX_QUERY_LIMIT)


class IntegrityReportResponse(BaseModel):
    investigation_id: uuid.UUID
    orphans: list[dict[str, Any]]
    cycles: list[dict[str, Any]]
    confidence_anomalies: list[dict[str, Any]]
    provenance_gaps: list[dict[str, Any]]
    stale_enrichments: list[dict[str, Any]]
    has_violations: bool


class TimelinePageResponse(BaseModel):
    investigation_id: uuid.UUID
    events: list[dict[str, Any]]
    limit: int
    offset: int
