"""Enrichment orchestration.

Owns the retry policy, per-provider timeout, per-provider circuit breaker,
and Redis-backed result cache. Each successful enrichment becomes a new
Evidence row + an IOC_ENRICHED event; failures emit ENRICHMENT_FAILED.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from core.events.emitter import EventEmitter
from core.events.types import EventType
from evidence.models import Evidence, Provenance
from evidence.provenance import ProvenanceLevel
from evidence.store import EvidenceStore
from investigation.enrichment.provider import EnrichmentProvider, EnrichmentResult
from investigation.enrichment.registry import ProviderRegistry
from resolution.service import ResolvedEntity
from storage.postgres.models.enrichment_result import EnrichmentResultRow

if TYPE_CHECKING:
    from core.cache.redis import RedisClient
    from core.database.postgres import Database

log = structlog.get_logger(__name__)


_MAX_RETRIES = 3
_BREAKER_THRESHOLD = 5
_BREAKER_OPEN_SECONDS = 30
_BREAKER_FAILURE_TTL_SECONDS = 60


@dataclass(frozen=True)
class _CircuitBreaker:
    """Tiny Redis-backed breaker. State lives in two keys per provider."""

    redis: RedisClient
    provider_name: str

    def _state_key(self) -> str:
        return f"cb:{self.provider_name}:state"

    def _failures_key(self) -> str:
        return f"cb:{self.provider_name}:failures"

    async def is_open(self) -> bool:
        state = await self.redis.client.get(self._state_key())
        return state is not None

    async def record_success(self) -> None:
        await self.redis.client.delete(self._state_key(), self._failures_key())

    async def record_failure(self) -> None:
        count = await self.redis.client.incr(self._failures_key())
        await self.redis.client.expire(self._failures_key(), _BREAKER_FAILURE_TTL_SECONDS)
        if count >= _BREAKER_THRESHOLD:
            await self.redis.client.setex(self._state_key(), _BREAKER_OPEN_SECONDS, b"OPEN")
            log.warning(
                "circuit_breaker.opened",
                provider=self.provider_name,
                threshold=_BREAKER_THRESHOLD,
            )


class EnrichmentExecutor:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        database: Database,
        redis: RedisClient,
        evidence_store: EvidenceStore,
        event_emitter: EventEmitter,
    ) -> None:
        self._registry = registry
        self._database = database
        self._redis = redis
        self._evidence_store = evidence_store
        self._event_emitter = event_emitter

    async def enrich(
        self,
        entity: ResolvedEntity,
        *,
        investigation_id: uuid.UUID,
        ioc_evidence_id: uuid.UUID,
        chain_of_custody: list[uuid.UUID],
    ) -> list[EnrichmentResult]:
        providers = self._registry.providers_for(entity.entity_type)
        if not providers:
            log.info(
                "enrichment.no_providers",
                entity_type=entity.entity_type.value,
                entity_id=str(entity.entity_id),
            )
            return []

        tasks = [
            self._run_one(p, entity, investigation_id, ioc_evidence_id, chain_of_custody)
            for p in providers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return [r for r in results if r is not None]

    async def _run_one(
        self,
        provider: EnrichmentProvider,
        entity: ResolvedEntity,
        investigation_id: uuid.UUID,
        ioc_evidence_id: uuid.UUID,
        chain_of_custody: list[uuid.UUID],
    ) -> EnrichmentResult | None:
        breaker = _CircuitBreaker(self._redis, provider.name)
        if await breaker.is_open():
            log.info("enrichment.skipped_breaker_open", provider=provider.name)
            return None

        cache_key = f"enrichment:{provider.name}:{entity.entity_id}"
        cached = await self._redis.client.get(cache_key)
        if cached:
            try:
                payload = json.loads(cached)
                return EnrichmentResult(
                    provider=provider.name,
                    success=True,
                    data=payload,
                    fetched_at=datetime.now(timezone.utc),
                )
            except (json.JSONDecodeError, TypeError):
                pass

        result = await self._fetch_with_retries(provider, entity)
        if result.success:
            await breaker.record_success()
            await self._redis.client.setex(
                cache_key, provider.cache_ttl_seconds, json.dumps(result.data).encode()
            )
            await self._persist_success(
                provider, entity, result, investigation_id, ioc_evidence_id, chain_of_custody
            )
        else:
            await breaker.record_failure()
            await self._persist_failure(provider, entity, result, investigation_id, ioc_evidence_id)

        return result

    async def _fetch_with_retries(
        self,
        provider: EnrichmentProvider,
        entity: ResolvedEntity,
    ) -> EnrichmentResult:
        last_error: str | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await asyncio.wait_for(
                    provider.enrich(entity), timeout=provider.timeout_seconds
                )
            except asyncio.TimeoutError:
                last_error = f"timeout after {provider.timeout_seconds}s"
                log.warning(
                    "enrichment.timeout",
                    provider=provider.name,
                    attempt=attempt,
                    entity_id=str(entity.entity_id),
                )
            except Exception as e:  # noqa: BLE001 — provider faults are treated uniformly
                last_error = f"{type(e).__name__}: {e}"
                log.warning(
                    "enrichment.error",
                    provider=provider.name,
                    attempt=attempt,
                    error=last_error,
                    entity_id=str(entity.entity_id),
                )
            await asyncio.sleep(min(2 ** (attempt - 1), 4))
        return EnrichmentResult(
            provider=provider.name,
            success=False,
            data={},
            error=last_error,
        )

    async def _persist_success(
        self,
        provider: EnrichmentProvider,
        entity: ResolvedEntity,
        result: EnrichmentResult,
        investigation_id: uuid.UUID,
        ioc_evidence_id: uuid.UUID,
        chain_of_custody: list[uuid.UUID],
    ) -> None:
        async with self._database.session() as session:
            evidence = Evidence(
                source=provider.name,
                type=entity.entity_type.value,
                raw_data=result.data,
                normalized_data={},
                confidence=provider.reliability,
                provenance=Provenance(
                    level=ProvenanceLevel.PRIMARY_SOURCE,
                    source_reliability=provider.reliability,
                    extraction_method=f"{provider.name}_lookup",
                    chain_of_custody=list(chain_of_custody),
                ),
                linked_entities=[entity.entity_id],
                investigation_id=investigation_id,
            )
            evidence_id = await self._evidence_store.record(session, evidence)
            await self._event_emitter.emit(
                session,
                EventType.IOC_ENRICHED,
                source=f"enrichment.{provider.name}",
                investigation_id=investigation_id,
                target=entity.canonical_form,
                evidence_refs=[evidence_id, ioc_evidence_id],
                metadata={
                    "provider": provider.name,
                    "reliability": provider.reliability,
                    "reputation": result.data.get("reputation"),
                },
                confidence=provider.reliability,
            )
            session.add(
                EnrichmentResultRow(
                    id=uuid.uuid4(),
                    ioc_evidence_id=ioc_evidence_id,
                    provider=provider.name,
                    request_fingerprint=f"{provider.name}:{entity.entity_id}:{int(time.time() // 86400)}",
                    raw_response=result.data,
                    success=True,
                    error=None,
                    timestamp=result.fetched_at,
                )
            )
            await session.commit()

    async def _persist_failure(
        self,
        provider: EnrichmentProvider,
        entity: ResolvedEntity,
        result: EnrichmentResult,
        investigation_id: uuid.UUID,
        ioc_evidence_id: uuid.UUID,
    ) -> None:
        async with self._database.session() as session:
            await self._event_emitter.emit(
                session,
                EventType.ENRICHMENT_FAILED,
                source=f"enrichment.{provider.name}",
                investigation_id=investigation_id,
                target=entity.canonical_form,
                evidence_refs=[ioc_evidence_id],
                metadata={"provider": provider.name, "error": result.error},
                confidence=0.0,
            )
            session.add(
                EnrichmentResultRow(
                    id=uuid.uuid4(),
                    ioc_evidence_id=ioc_evidence_id,
                    provider=provider.name,
                    request_fingerprint=f"{provider.name}:{entity.entity_id}:{int(time.time() // 86400)}",
                    raw_response={},
                    success=False,
                    error=result.error,
                    timestamp=result.fetched_at,
                )
            )
            await session.commit()
