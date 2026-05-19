"""Canonical Neo4j node types.

The set is fixed by the Phase 3 brief. Adding a new type is a schema change:
update this enum AND update :mod:`graph.governance.matrix` so the
Relationship Matrix knows which edges are allowed for the new type.

Mapping from the Phase 2 :class:`resolution.types.EntityType` (which is the
IOC taxonomy) into this taxonomy is in :func:`from_entity_type` below.
"""
from __future__ import annotations

from enum import Enum

from resolution.types import EntityType


class NodeType(str, Enum):
    USER = "User"
    IP = "IP"
    DOMAIN = "Domain"
    URL = "URL"
    HASH = "Hash"
    EMAIL = "Email"
    INVESTIGATION = "Investigation"
    ALERT = "Alert"
    PROMPT = "Prompt"
    AGENT = "Agent"
    WORKFLOW = "Workflow"
    FINDING = "Finding"
    EVIDENCE = "Evidence"


# IOC sub-taxonomy from Phase 2 collapses into the broader graph node types.
# (Hashes share a single Hash label with a ``hash_algo`` property; URLs and
# Domains stay distinct because the Relationship Matrix treats them
# differently.)
_ENTITY_TO_NODE: dict[EntityType, NodeType] = {
    EntityType.DOMAIN: NodeType.DOMAIN,
    EntityType.URL: NodeType.URL,
    EntityType.IP: NodeType.IP,
    EntityType.EMAIL: NodeType.EMAIL,
    EntityType.HASH_MD5: NodeType.HASH,
    EntityType.HASH_SHA1: NodeType.HASH,
    EntityType.HASH_SHA256: NodeType.HASH,
}


def from_entity_type(entity_type: EntityType) -> NodeType | None:
    """Return the graph NodeType for a Phase 2 EntityType, or None if the
    entity is not graphable (e.g., RAW_LOG, JSON_PAYLOAD, CVE).

    Returning None is a deliberate signal — non-graphable Evidence still
    becomes an :data:`NodeType.EVIDENCE` node, but it is not duplicated as
    an entity node.
    """
    return _ENTITY_TO_NODE.get(entity_type)
