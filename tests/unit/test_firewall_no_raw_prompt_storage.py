"""Static enforcement of CLAUDE.md invariant #12: the firewall_events
table NEVER stores raw prompt or response text.

If a future PR adds a column called e.g. ``prompt_text`` or
``raw_prompt`` this test fails immediately, before any data is written.
The check inspects the SQLAlchemy ``__table__`` metadata so it doesn't
need a live database.
"""
from __future__ import annotations

from storage.postgres.models.firewall_event import FirewallEvent


_FORBIDDEN_SUBSTRINGS = (
    "prompt_text",
    "response_text",
    "raw_prompt",
    "raw_response",
    "plaintext",
)


def test_firewall_event_has_no_raw_text_columns() -> None:
    bad = [
        c.name
        for c in FirewallEvent.__table__.columns
        if any(s in c.name.lower() for s in _FORBIDDEN_SUBSTRINGS)
    ]
    assert not bad, f"firewall_events has forbidden columns: {bad}"


def test_firewall_event_only_carries_fingerprint_columns() -> None:
    cols = {c.name for c in FirewallEvent.__table__.columns}
    assert "prompt_sha256" in cols
    assert "response_sha256" in cols
