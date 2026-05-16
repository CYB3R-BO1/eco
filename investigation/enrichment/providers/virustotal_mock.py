"""Mock VirusTotal-compatible provider.

Supports every IOC type so we always get at least one enrichment per IOC.
Output is keyed on the canonical form to keep tests stable.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import ClassVar

from investigation.enrichment.provider import EnrichmentProvider, EnrichmentResult
from resolution.service import ResolvedEntity
from resolution.types import EntityType


class VirusTotalMockProvider(EnrichmentProvider):
    name: ClassVar[str] = "VirusTotal"
    reliability: ClassVar[float] = 0.95
    timeout_seconds: ClassVar[float] = 8.0
    cache_ttl_seconds: ClassVar[int] = 6 * 3600
    supported_types: ClassVar[set[EntityType]] = {
        EntityType.URL,
        EntityType.DOMAIN,
        EntityType.IP,
        EntityType.HASH_MD5,
        EntityType.HASH_SHA1,
        EntityType.HASH_SHA256,
    }

    async def enrich(self, entity: ResolvedEntity) -> EnrichmentResult:
        await asyncio.sleep(0)
        seed = int(hashlib.md5(entity.canonical_form.encode()).hexdigest()[:8], 16)
        # Deterministic detection rate: mostly clean, occasionally malicious.
        detection_count = seed % 73 if seed % 7 == 0 else 0
        reputation = (
            "malicious" if detection_count > 30
            else "suspicious" if detection_count > 5
            else "clean"
        )
        return EnrichmentResult(
            provider=self.name,
            success=True,
            data={
                "indicator": entity.canonical_form,
                "type": entity.entity_type.value,
                "detection_count": detection_count,
                "total_engines": 73,
                "reputation": reputation,
                "last_analysis_date": "2024-05-01T00:00:00Z",
            },
        )
