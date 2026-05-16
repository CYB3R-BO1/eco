"""Evidence domain model.

Matches PLAN.md §3 exactly. ``EvidenceStore`` works exclusively with this
type — the ORM ``EvidenceRow`` is a private storage detail. A new evidence
record without ``id`` is OK on the way in; ``record()`` fills it in and
returns the persisted form.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evidence.provenance import ProvenanceLevel


class Provenance(BaseModel):
    """Per-Evidence provenance record.

    ``chain_of_custody`` is the ordered list of event IDs that produced this
    evidence — required so a forensic auditor can replay how a finding came
    to exist. Empty is allowed only for USER_SUPPLIED ingest evidence, which
    is the head of every chain.
    """

    level: ProvenanceLevel
    source_reliability: float = Field(ge=0.0, le=1.0)
    extraction_method: str
    chain_of_custody: list[uuid.UUID] = Field(default_factory=list)


class Evidence(BaseModel):
    """The unit currency of the Evidence Engine."""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str
    type: str  # entity_type or "raw_log" / "json_payload"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: dict[str, Any] = Field(default_factory=dict)
    normalized_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    linked_entities: list[uuid.UUID] = Field(default_factory=list)
    investigation_id: uuid.UUID | None = None
