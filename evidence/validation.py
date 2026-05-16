"""Evidence-level validators.

Pydantic catches simple type/range issues; this module enforces the
cross-field invariants that Pydantic alone can't express. ``validate()`` is
called by ``EvidenceStore.record`` immediately before INSERT — if it raises
``EvidenceValidationError`` the write is rejected with no DB side effects.
"""
from __future__ import annotations

from evidence.models import Evidence
from evidence.provenance import ProvenanceLevel


class EvidenceValidationError(ValueError):
    """Raised when an Evidence record violates a structural invariant."""


def validate(evidence: Evidence) -> None:
    """Cross-field validity check.

    * ``chain_of_custody`` must be non-empty unless the level is USER_SUPPLIED.
      Every derived/AI/primary observation is *caused* by something — that
      something is the head of the chain.
    * ``raw_data`` must be non-empty (an empty observation isn't evidence).
    """
    if (
        evidence.provenance.level is not ProvenanceLevel.USER_SUPPLIED
        and not evidence.provenance.chain_of_custody
    ):
        raise EvidenceValidationError(
            f"chain_of_custody required for provenance level {evidence.provenance.level.value}"
        )
    if not evidence.raw_data and not evidence.normalized_data:
        raise EvidenceValidationError("evidence must have raw_data or normalized_data")
