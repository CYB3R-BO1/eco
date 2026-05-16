from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.events.types import EventType
from investigation.lifecycle.states import InvestigationState


class TimelineEntry(BaseModel):
    event_id: uuid.UUID
    event_type: EventType
    timestamp: datetime
    source: str
    actor: str
    target: str | None
    evidence_refs: list[uuid.UUID]
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict, alias="event_metadata")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class InvestigationResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: InvestigationState
    severity: str
    summary: str | None
    confidence_score: float
    schema_version: int
    created_at: datetime
    updated_at: datetime
    evidence_refs: list[uuid.UUID]
    timeline: list[TimelineEntry]
