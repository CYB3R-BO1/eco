"""Relationship Matrix sanity tests.

These tests prove the matrix data is well-formed and that the headline
combinations from PLAN.md §6 are present. They are pure data tests — no
DB, no Neo4j, no fixtures.
"""
from __future__ import annotations

from graph.governance.matrix import (
    RELATIONSHIP_MATRIX,
    allowed_targets,
    is_allowed,
)
from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType


def test_matrix_is_frozen_at_module_load() -> None:
    """Every value in the matrix should be a frozenset so callers cannot
    mutate the allowlist at runtime."""
    for value in RELATIONSHIP_MATRIX.values():
        assert isinstance(value, frozenset), type(value)


def test_ip_resolves_to_domain_is_allowed() -> None:
    assert is_allowed(NodeType.IP, RelationshipType.RESOLVES_TO, NodeType.DOMAIN)


def test_domain_resolves_to_ip_is_allowed() -> None:
    assert is_allowed(NodeType.DOMAIN, RelationshipType.RESOLVES_TO, NodeType.IP)


def test_hash_resolves_to_email_is_rejected() -> None:
    """Sanity — Hash never resolves to anything; rejecting this is the
    headline negative case."""
    assert not is_allowed(NodeType.HASH, RelationshipType.RESOLVES_TO, NodeType.EMAIL)


def test_unknown_rel_for_source_returns_empty_set() -> None:
    """A relationship not defined for the source type returns no targets,
    which our validator treats as a hard reject."""
    targets = allowed_targets(NodeType.HASH, RelationshipType.RESOLVES_TO)
    assert targets == frozenset()


def test_part_of_investigation_is_universal() -> None:
    """Every IOC and Evidence node should be reachable via PART_OF →
    Investigation — that's how investigation_subgraph() finds them."""
    for source in (
        NodeType.IP,
        NodeType.DOMAIN,
        NodeType.URL,
        NodeType.HASH,
        NodeType.EMAIL,
        NodeType.USER,
        NodeType.EVIDENCE,
        NodeType.FINDING,
        NodeType.ALERT,
    ):
        assert NodeType.INVESTIGATION in allowed_targets(source, RelationshipType.PART_OF), source


def test_firewall_relationships_are_present() -> None:
    """Phase 4 will wire writers for Prompt → Agent edges; Phase 3 must at
    least schema-accept them so that work doesn't require a matrix update."""
    assert is_allowed(NodeType.PROMPT, RelationshipType.ANALYZED_BY, NodeType.AGENT)
    assert is_allowed(NodeType.PROMPT, RelationshipType.BLOCKED, NodeType.AGENT)
    assert is_allowed(NodeType.PROMPT, RelationshipType.TRIGGERED, NodeType.ALERT)


def test_url_part_of_domain_and_investigation() -> None:
    """URL has two legal PART_OF targets: the parent Domain and the
    enclosing Investigation. Both must be present in the matrix."""
    targets = allowed_targets(NodeType.URL, RelationshipType.PART_OF)
    assert NodeType.DOMAIN in targets
    assert NodeType.INVESTIGATION in targets


def test_every_relationship_type_appears_somewhere() -> None:
    """If a RelationshipType has zero matrix entries it's dead vocabulary
    — that's a smell worth catching at test time."""
    seen: set[RelationshipType] = set()
    for (_, rel), _ in RELATIONSHIP_MATRIX.items():
        seen.add(rel)
    for rel in RelationshipType:
        assert rel in seen, f"RelationshipType.{rel.name} has no matrix entries"
