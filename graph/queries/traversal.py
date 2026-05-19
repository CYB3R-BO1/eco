"""Cypher templates for graph reads.

All traversals are depth-bounded and limit-bounded. The depth value is
expressed as a Cypher-side literal because Neo4j does not allow parameter
substitution inside the ``*1..N`` variable-length path syntax — but the
caller is expected to have validated ``depth`` via
:meth:`SchemaValidator.validate_traversal_depth` before reaching here, and
the value is interpolated only as an int (never from user-controlled
strings).
"""
from __future__ import annotations


def node_neighborhood(depth: int) -> str:
    """All nodes reachable from a starting node within ``depth`` hops,
    plus the edges connecting them.

    Returns a single record per outgoing/incoming relationship within the
    subgraph; the caller flattens to deduped node + edge lists.
    """
    if not isinstance(depth, int) or depth < 1:
        raise ValueError("depth must be a positive integer")
    return (
        "MATCH (start {id: $node_id}) "
        f"OPTIONAL MATCH path = (start)-[*1..{depth}]-(neighbor) "
        "WITH start, collect(DISTINCT path) AS paths "
        "UNWIND paths AS p "
        "WITH start, p, relationships(p) AS rels, nodes(p) AS ns "
        "RETURN start, ns AS nodes, rels AS rels "
        "LIMIT $limit"
    )


def investigation_subgraph() -> str:
    """The full subgraph anchored at an Investigation node.

    Every Phase 3 graph write attaches IOCs / Evidence / Findings to the
    Investigation via :data:`PART_OF`, so this single pattern collects the
    whole story.
    """
    return (
        "MATCH (i:Investigation {id: $investigation_id}) "
        "OPTIONAL MATCH (i)<-[:PART_OF]-(member) "
        "OPTIONAL MATCH (member)-[r]-(other) "
        "WHERE other = i OR (other)-[:PART_OF]->(i) "
        "WITH i, collect(DISTINCT member) AS members, "
        "     collect(DISTINCT r) AS rels "
        "RETURN i AS investigation, members AS members, rels AS rels"
    )


def node_with_neighbors() -> str:
    """One-hop neighborhood for the GET /graph/node/{id} endpoint."""
    return (
        "MATCH (n {id: $node_id}) "
        "OPTIONAL MATCH (n)-[out]->(succ) "
        "OPTIONAL MATCH (n)<-[inc]-(pred) "
        "WITH n, "
        "     collect(DISTINCT {edge: out, other: succ}) AS outgoing, "
        "     collect(DISTINCT {edge: inc, other: pred}) AS incoming "
        "RETURN n AS node, outgoing, incoming"
    )


def dsl_query(depth: int, rel_filter_clause: str) -> str:
    """The structured POST /graph/query template.

    ``rel_filter_clause`` is rendered from the validated RelationshipType
    enum values by :func:`render_rel_filter`. Confidence is filtered on the
    Cypher side so cheap rejections don't waste round trips.
    """
    if not isinstance(depth, int) or depth < 1:
        raise ValueError("depth must be a positive integer")
    return (
        "MATCH (start {id: $start_node_id}) "
        f"OPTIONAL MATCH path = (start)-[{rel_filter_clause}*1..{depth}]-(node) "
        "WITH start, path, relationships(path) AS rels, nodes(path) AS ns "
        "WHERE all(r IN rels WHERE coalesce(r.confidence, 0) >= $min_confidence) "
        "RETURN start, ns AS nodes, rels AS rels "
        "LIMIT $limit"
    )


def render_rel_filter(rel_values: list[str]) -> str:
    """Render a pipe-separated rel-type filter ``:A|B|C``.

    Empty input means "any relationship type" → empty string (which
    interpolates as ``[*1..N]`` without a label filter). Values are
    enum-derived and therefore safe to interpolate.
    """
    if not rel_values:
        return ""
    return ":" + "|".join(rel_values)


# Read used by the cardinality check before MERGE; lives here rather than in
# mutations.py because it's a *read*, even though it's used during writes.
COUNT_OUT_RELS_BY_TYPE = (
    "MATCH (n {id: $node_id})-[r]->() "
    "RETURN type(r) AS rel_type, count(r) AS cnt"
)
