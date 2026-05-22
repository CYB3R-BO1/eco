"""Authenticated request principal (Phase 6 WP3).

A :class:`Principal` is the immutable identity attached to a request after
the bearer token has been verified. It is the input to every RBAC check
(WP4): roles + scopes are evaluated against the route's required
permission; ``subject`` is bound to log contextvars so every downstream
line is auto-tagged.

Why a frozen dataclass and not a Pydantic model: this object is created
on every request, never serialized over the wire, and must compare by
value for tests. ``frozen=True`` also prevents accidental mutation
mid-request — a route handler cannot promote itself to admin.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    role: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    token_kid: str = ""

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
