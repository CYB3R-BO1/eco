"""Static guarantees about the public surface of GraphService.

Phase 1's GraphService exposed ``run_read`` / ``run_write`` raw-Cypher
methods. Phase 3 removes those. If they ever creep back in, this test
fails — that's the line of defense against the "centralized mutation"
invariant slowly being eroded by a well-intentioned PR.
"""
from __future__ import annotations

from graph.graph_service.mutations import GraphMutator
from graph.graph_service.service import GraphService


def test_graph_service_does_not_expose_raw_write() -> None:
    public = {name for name in dir(GraphService) if not name.startswith("_")}
    forbidden = {"run_write", "run_read", "execute_write", "execute_read"}
    assert forbidden.isdisjoint(public), public & forbidden


def test_graph_service_exposes_only_typed_helpers() -> None:
    public = {name for name in dir(GraphService) if not name.startswith("_")}
    required = {"mutator", "traverser", "integrity", "ping"}
    assert required.issubset(public), required - public


def test_mutator_has_typed_methods() -> None:
    public = {name for name in dir(GraphMutator) if not name.startswith("_")}
    required = {
        "upsert_node",
        "upsert_entity_node",
        "upsert_investigation_node",
        "upsert_evidence_node",
        "create_relationship",
    }
    assert required.issubset(public), required - public


def test_mutator_has_no_run_write() -> None:
    """The mutator is the closest thing we have to a raw-write surface,
    so the same hygiene check applies here too."""
    public = {name for name in dir(GraphMutator) if not name.startswith("_")}
    assert "run_write" not in public
    assert "execute_write" not in public
