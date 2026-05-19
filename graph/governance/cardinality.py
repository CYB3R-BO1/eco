"""Hard operational limits — PLAN.md §3.5.

These caps protect the graph from runaway traversals and from accidentally
turning a high-fanout node (e.g., a public IP) into an unbounded hub. The
limits are constants rather than configuration on purpose: relaxing them
silently is the kind of regression that surfaces only as a Neo4j outage,
so the change should be conspicuous in a code review.
"""
from __future__ import annotations


# Per PLAN.md §3.5 operational limits.
MAX_TRAVERSAL_DEPTH: int = 8
MAX_RELATIONSHIPS_PER_NODE: int = 1000
QUERY_TIMEOUT_SECONDS: int = 30

# Hard cap on the size of a single read response so a malicious or
# misconfigured caller can't pull the whole subgraph in one shot.
MAX_QUERY_LIMIT: int = 1000
