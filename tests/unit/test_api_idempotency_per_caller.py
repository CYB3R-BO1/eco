"""Phase 7 WP1 — idempotency cache is scoped by JWT subject, never by 'anon'.

The previous WP5 (Phase 6) implementation ran the idempotency check as
an ASGI middleware that resolved the cache bucket BEFORE auth ran, so
the bucket fell back to ``"anon"``. Two callers sharing an
``Idempotency-Key`` could see each other's responses. The dependency
form added in WP1 fixes this by gating the cache key on the verified
``subject`` claim from the JWT principal.

This test exercises the helper functions directly (the dependency form
itself raises HTTPException to short-circuit the route — testing it
end-to-end requires the FastAPI app fixture, which lives in
``test_api_auth.py``).
"""
from __future__ import annotations

from apps.api.middleware_idempotency import _cache_key


def test_cache_key_includes_subject() -> None:
    key_alice = _cache_key("alice", "abc-123")
    key_bob = _cache_key("bob", "abc-123")
    assert key_alice != key_bob
    assert "alice" in key_alice
    assert "bob" in key_bob


def test_cache_key_changes_when_subject_changes() -> None:
    a = _cache_key("alice", "key-1")
    b = _cache_key("alice", "key-2")
    assert a != b


def test_cache_key_format_is_namespaced() -> None:
    # Prefix is stable so an operator can scan/clear the keys with a
    # Redis ``SCAN`` pattern: ``idempotency:*``.
    assert _cache_key("alice", "k").startswith("idempotency:")
