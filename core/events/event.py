"""Canonical Event domain model.

Matches PLAN.md §2 exactly. Events are immutable once persisted via
``EventEmitter`` — no field on this model has setters, and ``EventEmitter``
itself exposes no update or delete methods.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.events.types import EventType


class Event(BaseModel):
    """A single immutable event entry in the investigation timeline."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    investigation_id: uuid.UUID | None = None
    correlation_id: str | None = None
    actor: str = "system"
    target: str | None = None
    evidence_refs: list[uuid.UUID] = Field(default_factory=list)
    event_metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    confidence: float = 1.0
