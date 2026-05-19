"""Cypher templates for integrity verification.

Each check is a single query that returns the violating node/edge ids plus
diagnostic fields. The integrity module wraps these in
:class:`IntegrityReport` sections — the Cypher itself just answers
"which nodes are wrong?"
"""
from __future__ import annotations


# Orphan nodes within an investigation: degree 0 (excluding the
# Investigation node itself, which is the root).
ORPHANS_IN_INVESTIGATION = (
    "MATCH (i:Investigation {id: $investigation_id}) "
    "OPTIONAL MATCH (i)<-[:PART_OF]-(member) "
    "WHERE NOT (member)--() "
    "  AND member IS NOT NULL "
    "RETURN member.id AS node_id, labels(member) AS labels"
)


# Cycle detection on PART_OF / GENERATED chains. These edges should be DAG;
# a cycle indicates a corrupt write or AI reasoning that referenced its own
# ancestor. We bound the search depth to avoid runaway path explosion.
CYCLES_IN_INVESTIGATION = (
    "MATCH (i:Investigation {id: $investigation_id}) "
    "MATCH path = (n)-[:PART_OF|GENERATED*1..8]->(n) "
    "WHERE (n)-[:PART_OF]->(i) OR n = i "
    "RETURN DISTINCT n.id AS node_id, "
    "       [x IN nodes(path) | x.id] AS cycle "
    "LIMIT 50"
)


# Nodes whose confidence is out of [0, 1] or unset. (Neo4j stores numbers
# as doubles; NaN comparisons return false so we explicitly check for them.)
CONFIDENCE_OUT_OF_RANGE_NODES = (
    "MATCH (i:Investigation {id: $investigation_id})<-[:PART_OF]-(n) "
    "WHERE n.confidence IS NULL "
    "   OR n.confidence < 0 "
    "   OR n.confidence > 1 "
    "   OR n.confidence <> n.confidence "
    "RETURN n.id AS node_id, n.confidence AS confidence, labels(n) AS labels"
)


# Edge confidence anomalies: out-of-range OR exceeding the min of its
# endpoints' confidences (which would violate the weakest-link rule for
# inherited edges).
CONFIDENCE_ANOMALY_EDGES = (
    "MATCH (i:Investigation {id: $investigation_id}) "
    "MATCH (a)-[r]->(b) "
    "WHERE (a)-[:PART_OF*0..1]->(i) AND (b)-[:PART_OF*0..1]->(i) "
    "  AND (r.confidence IS NULL "
    "       OR r.confidence < 0 "
    "       OR r.confidence > 1 "
    "       OR r.confidence <> r.confidence) "
    "RETURN type(r) AS rel_type, a.id AS source, b.id AS target, "
    "       r.confidence AS confidence "
    "LIMIT 100"
)


# Evidence nodes with provenance > USER_SUPPLIED but no chain_of_custody.
# Evidence carries a ``chain_of_custody`` property (list of event ids); a
# DERIVED or PRIMARY Evidence without one is a provenance gap.
PROVENANCE_GAPS = (
    "MATCH (i:Investigation {id: $investigation_id})<-[:PART_OF]-(e:Evidence) "
    "WHERE e.provenance_level IS NOT NULL "
    "  AND e.provenance_level <> 'USER_SUPPLIED' "
    "  AND (e.chain_of_custody IS NULL OR size(e.chain_of_custody) = 0) "
    "RETURN e.id AS evidence_id, e.provenance_level AS level"
)


# Stale enrichment: Evidence nodes whose age exceeds the retention threshold
# for their provenance level. Threshold is passed as a parameter map so the
# integrity module owns the policy.
STALE_ENRICHMENTS = (
    "MATCH (i:Investigation {id: $investigation_id})<-[:PART_OF]-(e:Evidence) "
    "WHERE e.created_at < $cutoff "
    "  AND e.provenance_level = $level "
    "RETURN e.id AS evidence_id, "
    "       e.created_at AS created_at, "
    "       e.provenance_level AS level"
)
