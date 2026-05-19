"""Risk levels + scoring.

Scoring uses :func:`core.confidence.propagate.derived_relationship_confidence`
to combine per-rule signal severities — corroboration within a single
threat category raises the floor but is capped by the strongest single
signal, so a hundred low-severity hits never overpower one
high-severity hit.
"""
