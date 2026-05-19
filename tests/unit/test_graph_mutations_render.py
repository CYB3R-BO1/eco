"""Cypher template rendering — string-only assertions, no Neo4j.

These tests guard against two regressions:

1. A new label or relationship-type value not propagating into the
   rendered Cypher (which would silently write the wrong shape).
2. Templates accidentally accepting user-controlled depth values without
   the validator being in between.
"""
from __future__ import annotations

import pytest

from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType
from graph.queries.mutations import (
    create_relationship_cypher,
    upsert_node_cypher_no_apoc,
)
from graph.queries.traversal import (
    dsl_query,
    node_neighborhood,
    render_rel_filter,
)


def test_upsert_node_uses_correct_label() -> None:
    cypher = upsert_node_cypher_no_apoc(NodeType.INVESTIGATION)
    assert "(n:Investigation" in cypher
    assert "MERGE" in cypher
    # idempotency: ON MATCH must update updated_at
    assert "ON MATCH SET" in cypher


def test_upsert_node_for_each_type_renders() -> None:
    for label in NodeType:
        cypher = upsert_node_cypher_no_apoc(label)
        assert f"(n:{label.value}" in cypher


def test_create_relationship_uses_correct_type() -> None:
    cypher = create_relationship_cypher(RelationshipType.RESOLVES_TO)
    assert "[r:RESOLVES_TO {fingerprint: $fingerprint}]" in cypher
    assert "MERGE (a)-[r:RESOLVES_TO" in cypher


def test_create_relationship_for_each_type_renders() -> None:
    for rel in RelationshipType:
        cypher = create_relationship_cypher(rel)
        assert f"[r:{rel.value} " in cypher


def test_node_neighborhood_rejects_non_positive_depth() -> None:
    with pytest.raises(ValueError):
        node_neighborhood(0)
    with pytest.raises(ValueError):
        node_neighborhood(-3)


def test_node_neighborhood_embeds_depth_in_pattern() -> None:
    cypher = node_neighborhood(4)
    assert "[*1..4]" in cypher
    assert "$limit" in cypher


def test_render_rel_filter_empty_gives_empty_string() -> None:
    assert render_rel_filter([]) == ""


def test_render_rel_filter_joins_with_pipe() -> None:
    out = render_rel_filter(["RESOLVES_TO", "RELATED_TO"])
    assert out == ":RESOLVES_TO|RELATED_TO"


def test_dsl_query_includes_min_confidence_filter() -> None:
    cypher = dsl_query(3, ":RESOLVES_TO|RELATED_TO")
    assert "$min_confidence" in cypher
    assert "[:RESOLVES_TO|RELATED_TO*1..3]" in cypher
