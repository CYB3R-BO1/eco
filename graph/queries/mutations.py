"""Cypher mutation templates.

All node writes are ``MERGE (n:Label {id: $id})`` so replays produce no
duplicates. All relationship writes are ``MERGE (a)-[r:REL {fingerprint:
$fp}]->(b)`` keyed on a deterministic fingerprint of ``(source_id, rel,
target_id)``; this gives us idempotent edge creation without relying on
Neo4j's relationship-uniqueness semantics (which require explicit
constraints per type).

The Cypher itself is parameterized only by node label and relationship
type, which come from validated enums (NodeType / RelationshipType) —
never from user input. So format-strings here are safe.
"""
from __future__ import annotations

from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType


def upsert_node_cypher(label: NodeType) -> str:
    """MERGE pattern for a node. Properties come from ``$props`` map.

    ``ON CREATE SET`` writes ``created_at``; ``ON MATCH SET`` writes
    ``updated_at`` so a replay leaves the original ``created_at`` alone but
    refreshes the rest. Confidence is the maximum of the existing value and
    the incoming value — corroborating evidence never lowers a node's
    confidence (lowering would let one weak source contradict prior strong
    ones).
    """
    return (
        f"MERGE (n:{label.value} {{id: $id}}) "
        "ON CREATE SET "
        "  n.created_at = $timestamp, "
        "  n.updated_at = $timestamp, "
        "  n += $props "
        "ON MATCH SET "
        "  n.updated_at = $timestamp, "
        "  n.confidence = CASE "
        "    WHEN coalesce(n.confidence, 0) >= coalesce($props.confidence, 0) "
        "    THEN n.confidence ELSE $props.confidence END, "
        "  n += apoc.map.removeKey($props, 'confidence') "
        "RETURN n.id AS id, "
        "       CASE WHEN n.created_at = $timestamp THEN true ELSE false END AS was_new"
    )


def upsert_node_cypher_no_apoc(label: NodeType) -> str:
    """MERGE pattern that does not require APOC.

    Used by default since we don't assume APOC is installed in the test
    Neo4j container. Properties are written via individual SET clauses,
    and confidence uses a CASE expression.
    """
    return (
        f"MERGE (n:{label.value} {{id: $id}}) "
        "ON CREATE SET n.created_at = $timestamp, n += $props "
        "ON MATCH SET "
        "  n.updated_at = $timestamp, "
        "  n.confidence = CASE "
        "    WHEN coalesce(n.confidence, 0) >= coalesce($props.confidence, 0) "
        "    THEN n.confidence ELSE coalesce($props.confidence, n.confidence) END "
        "WITH n "
        "SET n += $non_confidence_props "
        "RETURN n.id AS id, "
        "       CASE WHEN n.created_at = $timestamp THEN true ELSE false END AS was_new"
    )


def create_relationship_cypher(rel: RelationshipType) -> str:
    """MERGE a relationship between two existing nodes.

    Source and target are matched by ``id`` only, regardless of label —
    callers are expected to have validated the label pair via
    :class:`graph.governance.SchemaValidator` BEFORE calling this. Putting
    the type check in Cypher would push validation past the rejection
    audit log, which is the wrong order.

    Confidence on the edge uses the same "never lower" rule as nodes.
    """
    return (
        "MATCH (a {id: $source_id}), (b {id: $target_id}) "
        f"MERGE (a)-[r:{rel.value} {{fingerprint: $fingerprint}}]->(b) "
        "ON CREATE SET "
        "  r.created_at = $timestamp, "
        "  r.confidence = $confidence, "
        "  r.evidence_id = $evidence_id, "
        "  r.investigation_id = $investigation_id, "
        "  r.metadata = $metadata "
        "ON MATCH SET "
        "  r.confidence = CASE WHEN r.confidence >= $confidence "
        "                      THEN r.confidence ELSE $confidence END, "
        "  r.updated_at = $timestamp "
        "RETURN r.fingerprint AS fingerprint, "
        "       CASE WHEN r.created_at = $timestamp THEN true ELSE false END AS was_new"
    )


# Read-side: count outgoing relationships for cardinality enforcement.
COUNT_OUTGOING_RELATIONSHIPS = (
    "MATCH (n {id: $node_id})-[r]->() "
    "RETURN count(r) AS cnt"
)

# Health check: trivial query that exercises the session.
PING_CYPHER = "RETURN 1 AS ok"
