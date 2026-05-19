"""SchemaValidator behavior — accept / reject + depth bounds."""
from __future__ import annotations

import pytest

from graph.governance.cardinality import MAX_TRAVERSAL_DEPTH
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType
from graph.governance.validator import (
    GraphSchemaViolationError,
    SchemaValidator,
    TraversalLimitExceededError,
)


def test_accept_known_edge() -> None:
    v = SchemaValidator()
    result = v.validate_edge(NodeType.IP, RelationshipType.RESOLVES_TO, NodeType.DOMAIN)
    assert result.ok
    assert result.reason is None


def test_reject_unknown_edge_has_explanation() -> None:
    v = SchemaValidator()
    result = v.validate_edge(NodeType.HASH, RelationshipType.RESOLVES_TO, NodeType.EMAIL)
    assert not result.ok
    assert result.reason is not None
    assert "RESOLVES_TO" in result.reason or "resolves_to" in result.reason.lower()


def test_assert_edge_raises_on_reject() -> None:
    v = SchemaValidator()
    with pytest.raises(GraphSchemaViolationError) as exc_info:
        v.assert_edge(NodeType.HASH, RelationshipType.RESOLVES_TO, NodeType.EMAIL)
    assert exc_info.value.source is NodeType.HASH
    assert exc_info.value.rel is RelationshipType.RESOLVES_TO
    assert exc_info.value.target is NodeType.EMAIL


def test_assert_edge_silent_on_accept() -> None:
    v = SchemaValidator()
    v.assert_edge(NodeType.IP, RelationshipType.RESOLVES_TO, NodeType.DOMAIN)  # no raise


def test_depth_within_bounds_ok() -> None:
    SchemaValidator.validate_traversal_depth(1)
    SchemaValidator.validate_traversal_depth(MAX_TRAVERSAL_DEPTH)


def test_depth_zero_or_negative_rejected() -> None:
    with pytest.raises(TraversalLimitExceededError):
        SchemaValidator.validate_traversal_depth(0)
    with pytest.raises(TraversalLimitExceededError):
        SchemaValidator.validate_traversal_depth(-1)


def test_depth_above_cap_rejected() -> None:
    with pytest.raises(TraversalLimitExceededError) as exc_info:
        SchemaValidator.validate_traversal_depth(MAX_TRAVERSAL_DEPTH + 1)
    assert exc_info.value.maximum == MAX_TRAVERSAL_DEPTH
    assert exc_info.value.requested == MAX_TRAVERSAL_DEPTH + 1
