"""Provider registry — what providers can enrich what types."""
from __future__ import annotations

from investigation.enrichment.provider import EnrichmentProvider
from resolution.types import EntityType


class ProviderRegistry:
    def __init__(self, providers: list[EnrichmentProvider]) -> None:
        self._providers = list(providers)

    def all(self) -> list[EnrichmentProvider]:
        return list(self._providers)

    def providers_for(self, entity_type: EntityType) -> list[EnrichmentProvider]:
        return [p for p in self._providers if p.supports(entity_type)]
