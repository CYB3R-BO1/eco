"""Graph Schema Governance.

PLAN.md §6 + CLAUDE.md invariant #2. The Relationship Matrix here is the
authoritative allowlist of ``(source_type, relationship_type, target_type)``
combinations. ``GraphService`` consults :class:`SchemaValidator` before every
mutation; rejected attempts are persisted in ``graph_rejections`` and emit
a ``GRAPH_MUTATION_REJECTED`` audit event.
"""
from graph.governance.cardinality import (
    MAX_RELATIONSHIPS_PER_NODE,
    MAX_TRAVERSAL_DEPTH,
    QUERY_TIMEOUT_SECONDS,
)
from graph.governance.matrix import RELATIONSHIP_MATRIX
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType
from graph.governance.validator import (
    GraphSchemaViolationError,
    SchemaValidator,
    ValidationResult,
)

__all__ = [
    "MAX_RELATIONSHIPS_PER_NODE",
    "MAX_TRAVERSAL_DEPTH",
    "QUERY_TIMEOUT_SECONDS",
    "NodeType",
    "RelationshipType",
    "RELATIONSHIP_MATRIX",
    "SchemaValidator",
    "ValidationResult",
    "GraphSchemaViolationError",
]
