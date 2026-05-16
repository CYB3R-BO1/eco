"""Mock WHOIS provider.

Deterministic output keyed on the canonical form so tests are stable. Shape
matches what a real WHOIS provider would return so callers don't need to
change when we swap this for a live integration in a later phase.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import ClassVar

from investigation.enrichment.provider import EnrichmentProvider, EnrichmentResult
from resolution.service import ResolvedEntity
from resolution.types import EntityType


class WhoisMockProvider(EnrichmentProvider):
    name: ClassVar[str] = "WHOIS"
    reliability: ClassVar[float] = 0.90
    timeout_seconds: ClassVar[float] = 5.0
    cache_ttl_seconds: ClassVar[int] = 24 * 3600
    supported_types: ClassVar[set[EntityType]] = {EntityType.DOMAIN}

    async def enrich(self, entity: ResolvedEntity) -> EnrichmentResult:
        await asyncio.sleep(0)  # yield control; real I/O would await here
        seed = int(hashlib.md5(entity.canonical_form.encode()).hexdigest()[:8], 16)
        return EnrichmentResult(
            provider=self.name,
            success=True,
            data={
                "registrar": f"Mock Registrar {(seed % 5) + 1}",
                "creation_date": "2018-03-14",
                "expiry_date": "2026-03-14",
                "registrant_country": ["US", "DE", "GB", "FR", "JP"][seed % 5],
                "name_servers": ["ns1.mock.example", "ns2.mock.example"],
                "domain": entity.canonical_form,
            },
        )
