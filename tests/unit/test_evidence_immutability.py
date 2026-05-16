"""Static guarantees that EvidenceStore is write-once."""
from __future__ import annotations

import pytest

from evidence import EvidenceValidationError
from evidence.models import Evidence, Provenance
from evidence.provenance import ProvenanceLevel
from evidence.store import EvidenceStore
from evidence.validation import validate


def test_evidence_store_exposes_no_update_or_delete() -> None:
    """If this ever fails it means someone added a write path."""
    forbidden = {"update", "delete", "remove", "modify", "patch"}
    public = {name for name in dir(EvidenceStore) if not name.startswith("_")}
    assert forbidden.isdisjoint(public), public & forbidden


def test_user_supplied_allows_empty_chain_of_custody() -> None:
    ev = Evidence(
        source="user_supplied",
        type="raw_log",
        raw_data={"text": "sample"},
        confidence=0.9,
        provenance=Provenance(
            level=ProvenanceLevel.USER_SUPPLIED,
            source_reliability=0.5,
            extraction_method="ingest",
            chain_of_custody=[],
        ),
    )
    validate(ev)


def test_primary_source_requires_chain_of_custody() -> None:
    ev = Evidence(
        source="internal_extraction",
        type="ip",
        raw_data={"value": "8.8.8.8"},
        confidence=0.95,
        provenance=Provenance(
            level=ProvenanceLevel.PRIMARY_SOURCE,
            source_reliability=0.95,
            extraction_method="regex",
            chain_of_custody=[],
        ),
    )
    with pytest.raises(EvidenceValidationError):
        validate(ev)


def test_evidence_model_is_pydantic_strict() -> None:
    with pytest.raises(Exception):
        # confidence outside [0,1] must be rejected
        Evidence(
            source="x",
            type="y",
            raw_data={"a": 1},
            confidence=1.7,
            provenance=Provenance(
                level=ProvenanceLevel.USER_SUPPLIED,
                source_reliability=0.5,
                extraction_method="ingest",
            ),
        )
