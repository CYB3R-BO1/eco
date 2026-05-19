"""Layer 4 — composite rules engine.

A rule is a named predicate over the already-fired pattern + heuristic
signal set. When the predicate matches, the rule emits a single ``Signal``
of its own that carries the rule's severity and weight. Rules are the
hand-curated layer where domain expertise lives — "if X pattern AND Y
heuristic, escalate" — and where catalog-level :class:`Severity.CRITICAL`
gets attached.
"""
