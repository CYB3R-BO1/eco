"""Deterministic prompt sanitization.

When the policy engine returns SANITIZE, this package replaces flagged
spans with fixed marker strings (e.g. ``[EMAIL]``, ``[ROLE_TAG_REMOVED]``).
The transformation is *byte-deterministic*: the same prompt + signal
list always produces the same sanitized prompt. No LLM, no random
ordering, no time-dependent state.
"""
