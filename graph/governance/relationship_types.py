"""Canonical Neo4j relationship types.

Fixed by the Phase 3 brief. The Relationship Matrix in
:mod:`graph.governance.matrix` decides which ``(src_type, rel_type, dst_type)``
triples are legal — this enum is just the *vocabulary*.
"""
from __future__ import annotations

from enum import Enum


class RelationshipType(str, Enum):
    CONNECTED_TO = "CONNECTED_TO"
    RESOLVES_TO = "RESOLVES_TO"
    RELATED_TO = "RELATED_TO"
    GENERATED = "GENERATED"
    PART_OF = "PART_OF"
    ANALYZED_BY = "ANALYZED_BY"
    TRIGGERED = "TRIGGERED"
    BLOCKED = "BLOCKED"
