from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from resolution.types import EntityType


class IngestRequest(BaseModel):
    artifact: str | dict[str, Any] | list[Any]
    type: EntityType | None = None
    source_hint: str | None = None


class IngestResponse(BaseModel):
    investigation_id: uuid.UUID
    status: str
    evidence_id: uuid.UUID


class ExtractRequest(BaseModel):
    text: str | None = None
    json_payload: dict[str, Any] | list[Any] | None = Field(default=None, alias="json")
    types: list[EntityType] | None = None

    model_config = ConfigDict(populate_by_name=True)


class ExtractedIOCResponse(BaseModel):
    value: str
    canonical_form: str
    entity_type: EntityType
    extraction_method: str
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractResponse(BaseModel):
    extracted: list[ExtractedIOCResponse]
