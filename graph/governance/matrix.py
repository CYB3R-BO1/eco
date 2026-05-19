"""The Relationship Matrix — the only edges Neo4j will accept.

PLAN.md §6 specifies that ``(source_type, relationship_type, target_type)``
combinations must be on an allowlist. This module IS that allowlist.

Bypassing the matrix is invariant #2 of CLAUDE.md and the single biggest way
to corrupt graph quality: it produces nodes connected by relationships that
no traversal pattern was designed for, which means downstream queries break
or — worse — silently return wrong answers.

Schema additions require updating this matrix AND the relationship_types /
node_types enums. We deliberately keep the matrix dense and explicit (rather
than wildcard-heavy) so the legal shape of the graph is obvious from one
file.
"""
from __future__ import annotations

from typing import Final

from graph.governance.node_types import NodeType
from graph.governance.relationship_types import RelationshipType

_N = NodeType
_R = RelationshipType


# Map of (source_type, relationship_type) -> set of allowed target types.
# Use frozenset everywhere so callers can't mutate the matrix at runtime.
RELATIONSHIP_MATRIX: Final[dict[tuple[NodeType, RelationshipType], frozenset[NodeType]]] = {
    # --- Network / infrastructure correlations ----------------------------
    (_N.IP, _R.RESOLVES_TO): frozenset({_N.DOMAIN}),
    (_N.DOMAIN, _R.RESOLVES_TO): frozenset({_N.IP}),
    (_N.IP, _R.CONNECTED_TO): frozenset({_N.IP, _N.DOMAIN, _N.URL}),
    (_N.DOMAIN, _R.CONNECTED_TO): frozenset({_N.IP, _N.DOMAIN}),
    (_N.URL, _R.PART_OF): frozenset({_N.DOMAIN}),

    # --- Investigation / Evidence / IOC linkage ---------------------------
    # Every IOC node is PART_OF the investigation that surfaced it.
    (_N.IP, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.DOMAIN, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.URL, _R.PART_OF): frozenset({_N.INVESTIGATION, _N.DOMAIN}),
    (_N.HASH, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.EMAIL, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.USER, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.EVIDENCE, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.ALERT, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.FINDING, _R.PART_OF): frozenset({_N.INVESTIGATION}),
    (_N.PROMPT, _R.PART_OF): frozenset({_N.INVESTIGATION}),

    # Evidence references the entities it concerns. (Direction: Evidence
    # → Entity, because Evidence carries the link list.)
    (_N.EVIDENCE, _R.RELATED_TO): frozenset(
        {_N.IP, _N.DOMAIN, _N.URL, _N.HASH, _N.EMAIL, _N.USER, _N.EVIDENCE}
    ),

    # --- Generation: who/what produced a Finding or Evidence --------------
    (_N.AGENT, _R.GENERATED): frozenset({_N.FINDING, _N.EVIDENCE}),
    (_N.WORKFLOW, _R.GENERATED): frozenset({_N.FINDING, _N.EVIDENCE, _N.INVESTIGATION}),
    (_N.INVESTIGATION, _R.GENERATED): frozenset({_N.FINDING, _N.EVIDENCE, _N.ALERT}),

    # --- AI Firewall (Phase 4 wires the writers; Phase 3 schema-accepts) --
    (_N.PROMPT, _R.ANALYZED_BY): frozenset({_N.AGENT}),
    (_N.PROMPT, _R.TRIGGERED): frozenset({_N.ALERT, _N.WORKFLOW}),
    (_N.PROMPT, _R.BLOCKED): frozenset({_N.AGENT, _N.WORKFLOW}),
    (_N.AGENT, _R.PART_OF): frozenset({_N.WORKFLOW}),

    # --- Alerts -----------------------------------------------------------
    (_N.INVESTIGATION, _R.TRIGGERED): frozenset({_N.ALERT}),
    (_N.ALERT, _R.RELATED_TO): frozenset({_N.IP, _N.DOMAIN, _N.URL, _N.HASH, _N.EMAIL, _N.USER}),

    # --- User correlations ------------------------------------------------
    (_N.USER, _R.RELATED_TO): frozenset({_N.IP, _N.DOMAIN, _N.EMAIL, _N.URL}),

    # --- Generic correlation (kept narrow on purpose) ---------------------
    # RELATED_TO is the catch-all "we noticed these two together" edge.
    # Keep it limited to IOC-shaped pairs; if you find yourself wanting a
    # new RELATED_TO, ask whether the relationship deserves a real type.
    (_N.IP, _R.RELATED_TO): frozenset(
        {_N.IP, _N.DOMAIN, _N.URL, _N.HASH, _N.EMAIL, _N.USER, _N.ALERT}
    ),
    (_N.DOMAIN, _R.RELATED_TO): frozenset(
        {_N.IP, _N.DOMAIN, _N.URL, _N.HASH, _N.EMAIL, _N.USER, _N.ALERT}
    ),
    (_N.URL, _R.RELATED_TO): frozenset(
        {_N.IP, _N.DOMAIN, _N.URL, _N.HASH, _N.USER, _N.ALERT}
    ),
    (_N.HASH, _R.RELATED_TO): frozenset(
        {_N.IP, _N.DOMAIN, _N.URL, _N.HASH, _N.EMAIL, _N.ALERT}
    ),
    (_N.EMAIL, _R.RELATED_TO): frozenset({_N.IP, _N.DOMAIN, _N.URL, _N.USER, _N.ALERT}),

    # --- Finding cross-references ----------------------------------------
    (_N.FINDING, _R.RELATED_TO): frozenset({_N.FINDING, _N.EVIDENCE, _N.ALERT}),
}


def allowed_targets(source: NodeType, rel: RelationshipType) -> frozenset[NodeType]:
    """Return the set of legal target node types for ``(source, rel)``.

    Returns an empty frozenset if the pair has no entry — distinguishing
    *unknown* from *no allowed targets* isn't useful at the call site: both
    mean "this mutation is rejected."
    """
    return RELATIONSHIP_MATRIX.get((source, rel), frozenset())


def is_allowed(source: NodeType, rel: RelationshipType, target: NodeType) -> bool:
    return target in allowed_targets(source, rel)
