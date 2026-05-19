"""Policy engine — turns an analysis report into a single action.

The mapping is intentionally a pure function: same inputs → same output,
no I/O, no time-dependent state. That's what lets us hash the policy and
embed the hash in every decision so audits remain stable across future
policy changes.
"""
