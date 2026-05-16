"""Enrichment provider ABC.

Mock implementations in ``providers/`` and (later) real providers like
``virustotal_api.py`` will subclass this. The interface deliberately mirrors
what a production provider needs — timeout knob, supported types, reliability
score — so swapping mocks for live calls in a later phase is mechanical.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from resolution.service import ResolvedEntity
from resolution.types import EntityType


@dataclass(frozen=True)
class EnrichmentResult:
    provider: str
    success: bool
    data: dict[str, Any]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


class EnrichmentProvider(ABC):
    name: ClassVar[str]
    reliability: ClassVar[float]
    timeout_seconds: ClassVar[float] = 10.0
    cache_ttl_seconds: ClassVar[int] = 3600
    supported_types: ClassVar[set[EntityType]]

    def supports(self, entity_type: EntityType) -> bool:
        return entity_type in self.supported_types

    @abstractmethod
    async def enrich(self, entity: ResolvedEntity) -> EnrichmentResult: ...
