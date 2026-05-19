"""The four firewall actions.

Stored as a Postgres native enum (``firewall_action_enum``) on
``firewall_events.decision`` and surfaced verbatim on the API response
body. The action set is deliberately small — every action either reaches
the LLM (ALLOW, SANITIZE) or doesn't (BLOCK, REQUIRE_REVIEW). Anything
finer-grained belongs in the explainability payload, not in this enum.
"""
from __future__ import annotations

from enum import Enum


class FirewallAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    SANITIZE = "SANITIZE"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
