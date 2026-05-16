from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evidence.provenance import ProvenanceLevel


class ProvenanceResponse(BaseModel):
    level: ProvenanceLevel
    source_reliability: float
    extraction_method: str
    chain_of_custody: list[uuid.UUID]


class EvidenceResponse(BaseModel):
    evidence_id: uuid.UUID = Field(alias="id")
    source: str
    type: str
    timestamp: datetime
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    confidence: float
    provenance: ProvenanceResponse
    linked_entities: list[uuid.UUID]
    investigation_id: uuid.UUID | None

    model_config = ConfigDict(populate_by_name=True)
