"""FirewallGraphCorrelator — turns a recorded firewall decision into
Prompt / Agent / Workflow / Finding nodes and the matrix-approved edges
between them.

Uses :class:`graph.graph_service.service.GraphService` exclusively — no
direct Neo4j writes, no bypass of schema validation (CLAUDE.md invariant
#2).
"""
