"""SchemaValidator — runtime gate for every graph mutation.

GraphService calls :meth:`SchemaValidator.validate_edge` before every
relationship MERGE and :meth:`validate_traversal_depth` before every read.
Validation returns a :class:`ValidationResult` rather than raising on the
hot path so the caller can choose between raising and persisting a
rejection record for audit. The :class:`GraphSchemaViolationError` is for
sites that genuinely want a 409 propagation.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from graph.governance.cardinality import MAX_TRAVERSAL_DEPTH
from graph.governance.matrix import allowed_targets, is_allowed
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str | None = None

    @classmethod
    def accept(cls) -> "ValidationResult":
        return cls(ok=True, reason=None)

    @classmethod
    def reject(cls, reason: str) -> "ValidationResult":
        return cls(ok=False, reason=reason)


class GraphSchemaViolationError(ValueError):
    """Raised at the API boundary when a caller specifies an illegal edge.

    Internal correlation code prefers to ask for a :class:`ValidationResult`
    so that rejections can be persisted in ``graph_rejections`` rather than
    bubbling up as exceptions.
    """

    def __init__(
        self,
        source: NodeType,
        rel: RelationshipType,
        target: NodeType,
        reason: str,
    ) -> None:
        super().__init__(
            f"schema violation: ({source.value})-[{rel.value}]->({target.value}): {reason}"
        )
        self.source = source
        self.rel = rel
        self.target = target
        self.reason = reason


class TraversalLimitExceededError(ValueError):
    """Raised when a caller asks for a traversal deeper than allowed."""

    def __init__(self, requested: int, maximum: int) -> None:
        super().__init__(f"traversal depth {requested} exceeds maximum {maximum}")
        self.requested = requested
        self.maximum = maximum


class SchemaValidator:
    """Stateless. Cheap to call; safe to hold a single instance app-wide."""

    def validate_edge(
        self,
        source_type: NodeType,
        rel_type: RelationshipType,
        target_type: NodeType,
    ) -> ValidationResult:
        if is_allowed(source_type, rel_type, target_type):
            return ValidationResult.accept()

        allowed = allowed_targets(source_type, rel_type)
        if not allowed:
            reason = (
                f"relationship type {rel_type.value!r} is not defined for "
                f"source {source_type.value!r}"
            )
        else:
            reason = (
                f"target {target_type.value!r} not in allowed set "
                f"{{{', '.join(sorted(t.value for t in allowed))}}} for "
                f"({source_type.value})-[{rel_type.value}]->()"
            )
        log.warning(
            "graph.schema.rejected",
            source=source_type.value,
            rel=rel_type.value,
            target=target_type.value,
            reason=reason,
        )
        return ValidationResult.reject(reason)

    def assert_edge(
        self,
        source_type: NodeType,
        rel_type: RelationshipType,
        target_type: NodeType,
    ) -> None:
        result = self.validate_edge(source_type, rel_type, target_type)
        if not result.ok:
            raise GraphSchemaViolationError(
                source_type, rel_type, target_type, result.reason or "rejected"
            )

    @staticmethod
    def validate_traversal_depth(depth: int) -> None:
        if depth < 1 or depth > MAX_TRAVERSAL_DEPTH:
            raise TraversalLimitExceededError(depth, MAX_TRAVERSAL_DEPTH)
