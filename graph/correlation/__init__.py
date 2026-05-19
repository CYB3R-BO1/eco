"""CORRELATING phase orchestration.

Reads an investigation's Evidence + ResolvedEntity records from Postgres
and materializes them in Neo4j through :class:`GraphService`. Idempotent —
the underlying MERGEs make running the correlator twice produce zero new
nodes or edges.
"""
from graph.correlation.correlator import GraphCorrelator

__all__ = ["GraphCorrelator"]
