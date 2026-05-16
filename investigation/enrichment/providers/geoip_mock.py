"""Mock GeoIP provider."""
from __future__ import annotations

import asyncio
import hashlib
from typing import ClassVar

from investigation.enrichment.provider import EnrichmentProvider, EnrichmentResult
from resolution.service import ResolvedEntity
from resolution.types import EntityType

_COUNTRIES = ("US", "DE", "GB", "FR", "JP", "BR", "AU", "CA", "NL", "SG")
_CITIES = (
    "Mountain View", "Berlin", "London", "Paris", "Tokyo",
    "Sao Paulo", "Sydney", "Toronto", "Amsterdam", "Singapore",
)


class GeoIpMockProvider(EnrichmentProvider):
    name: ClassVar[str] = "GeoIP"
    reliability: ClassVar[float] = 0.85
    timeout_seconds: ClassVar[float] = 2.0
    cache_ttl_seconds: ClassVar[int] = 24 * 3600
    supported_types: ClassVar[set[EntityType]] = {EntityType.IP}

    async def enrich(self, entity: ResolvedEntity) -> EnrichmentResult:
        await asyncio.sleep(0)
        seed = int(hashlib.md5(entity.canonical_form.encode()).hexdigest()[:8], 16)
        idx = seed % len(_COUNTRIES)
        return EnrichmentResult(
            provider=self.name,
            success=True,
            data={
                "country": _COUNTRIES[idx],
                "city": _CITIES[idx],
                "asn": f"AS{(seed % 65535) + 1}",
                "organization": f"Mock ISP {(seed % 20) + 1}",
                "ip": entity.canonical_form,
            },
        )
