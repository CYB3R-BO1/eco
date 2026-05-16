"""Mock DNS provider."""
from __future__ import annotations

import asyncio
import hashlib
from typing import ClassVar

from investigation.enrichment.provider import EnrichmentProvider, EnrichmentResult
from resolution.service import ResolvedEntity
from resolution.types import EntityType


class DnsMockProvider(EnrichmentProvider):
    name: ClassVar[str] = "DNS"
    reliability: ClassVar[float] = 0.95
    timeout_seconds: ClassVar[float] = 3.0
    cache_ttl_seconds: ClassVar[int] = 3600
    supported_types: ClassVar[set[EntityType]] = {EntityType.DOMAIN, EntityType.URL}

    async def enrich(self, entity: ResolvedEntity) -> EnrichmentResult:
        await asyncio.sleep(0)
        h = hashlib.md5(entity.canonical_form.encode()).hexdigest()
        octets = [int(h[i : i + 2], 16) for i in range(0, 8, 2)]
        a_record = ".".join(str(o) for o in octets)
        return EnrichmentResult(
            provider=self.name,
            success=True,
            data={
                "A": [a_record],
                "AAAA": [f"2606:2800:220:1:{h[:4]}:{h[4:8]}:{h[8:12]}:{h[12:16]}"],
                "MX": ["10 mail.mock.example"],
                "NS": ["ns1.mock.example", "ns2.mock.example"],
                "queried_for": entity.canonical_form,
            },
        )
