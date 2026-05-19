"""Ingestion pipeline.

The orchestrator for ``POST /iocs/ingest``. Synchronously creates the
Investigation + raw Evidence, emits the head events, then fans out the slow
work (extract + enrich) onto the BackgroundTaskRunner.

Why this shape:

* The user gets a 202 quickly with the investigation_id, even if enrichment
  takes seconds.
* The transactional boundary is tight: the synchronous prefix (CREATED state
  + USER_SUPPLIED evidence + INVESTIGATION_CREATED/IOC_INGESTED events +
  idempotency-key persist) all commits together. If the background flow
  later fails, the investigation transitions to FAILED but the head record
  survives — auditors can still see what was attempted.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.events.types import EventType
from evidence.models import Evidence, Provenance
from evidence.provenance import ProvenanceLevel
from evidence.store import EvidenceStore
from graph.correlation.correlator import GraphCorrelator
from graph.graph_service.service import GraphService
from investigation.background import BackgroundTaskRunner
from investigation.enrichment.executor import EnrichmentExecutor
from investigation.extraction.extractor import ExtractedIOC, extract_iocs
from investigation.extraction.json_walker import extract_iocs_from_json
from investigation.ingestion.validation import IngestValidationError, validate_payload
from investigation.lifecycle.manager import LifecycleManager
from investigation.lifecycle.states import InvestigationState
from resolution.service import EntityResolutionService
from resolution.types import EntityType
from storage.postgres.models.idempotency_key import IdempotencyKeyRow
from storage.postgres.models.investigation import Investigation

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class IngestResult:
    investigation_id: uuid.UUID
    status: str
    evidence_id: uuid.UUID

    def to_json(self) -> dict[str, Any]:
        return {
            "investigation_id": str(self.investigation_id),
            "status": self.status,
            "evidence_id": str(self.evidence_id),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> IngestResult:
        return cls(
            investigation_id=uuid.UUID(data["investigation_id"]),
            status=data["status"],
            evidence_id=uuid.UUID(data["evidence_id"]),
        )


class IngestionPipeline:
    def __init__(
        self,
        *,
        database: Database,
        evidence_store: EvidenceStore,
        event_emitter: EventEmitter,
        resolver: EntityResolutionService,
        enrichment_executor: EnrichmentExecutor,
        lifecycle_manager: LifecycleManager,
        background_runner: BackgroundTaskRunner,
        graph_correlator: GraphCorrelator,
        graph_service: GraphService,
    ) -> None:
        self._db = database
        self._evidence = evidence_store
        self._events = event_emitter
        self._resolver = resolver
        self._enrichment = enrichment_executor
        self._lifecycle = lifecycle_manager
        self._runner = background_runner
        self._correlator = graph_correlator
        self._graph = graph_service

    async def ingest(
        self,
        artifact: str | dict[str, Any] | list[Any],
        *,
        declared_type: EntityType | None = None,
        source_hint: str | None = None,
        idempotency_key: str | None = None,
    ) -> IngestResult:
        validate_payload(artifact, declared_type)

        async with self._db.session() as session:
            if idempotency_key:
                cached = await session.get(IdempotencyKeyRow, idempotency_key)
                if cached is not None:
                    log.info("ingest.idempotent_replay", key=idempotency_key)
                    return IngestResult.from_json(cached.response)

            result = await self._create_head(session, artifact, declared_type, source_hint)

            if idempotency_key:
                session.add(
                    IdempotencyKeyRow(
                        key=idempotency_key,
                        response=result.to_json(),
                        created_at=datetime.now(timezone.utc),
                    )
                )
            await session.commit()

        self._runner.run(
            self._process(result.investigation_id, result.evidence_id, artifact, declared_type),
            name=f"ingest-{result.investigation_id}",
        )
        return result

    async def _create_head(
        self,
        session: AsyncSession,
        artifact: str | dict[str, Any] | list[Any],
        declared_type: EntityType | None,
        source_hint: str | None,
    ) -> IngestResult:
        investigation = Investigation(
            id=uuid.uuid4(),
            title=_derive_title(artifact),
            status=InvestigationState.CREATED,
            severity="unknown",
            confidence_score=0.0,
        )
        session.add(investigation)
        await session.flush()

        raw_payload = (
            {"text": artifact}
            if isinstance(artifact, str)
            else {"json": artifact}
        )
        evidence = Evidence(
            source=source_hint or "user_supplied",
            type=(declared_type.value if declared_type else "raw_log"),
            raw_data=raw_payload,
            normalized_data={},
            confidence=0.95,
            provenance=Provenance(
                level=ProvenanceLevel.USER_SUPPLIED,
                source_reliability=0.50,
                extraction_method="ingest",
                chain_of_custody=[],
            ),
            linked_entities=[],
            investigation_id=investigation.id,
        )
        evidence_id = await self._evidence.record(session, evidence)

        await self._events.emit(
            session,
            EventType.INVESTIGATION_CREATED,
            source="ingestion",
            investigation_id=investigation.id,
            target=investigation.title,
            evidence_refs=[evidence_id],
            metadata={"source_hint": source_hint},
        )
        await self._events.emit(
            session,
            EventType.IOC_INGESTED,
            source="ingestion",
            investigation_id=investigation.id,
            target=investigation.title,
            evidence_refs=[evidence_id],
            metadata={"declared_type": declared_type.value if declared_type else None},
        )
        return IngestResult(
            investigation_id=investigation.id,
            status=InvestigationState.CREATED.value,
            evidence_id=evidence_id,
        )

    async def _process(
        self,
        investigation_id: uuid.UUID,
        head_evidence_id: uuid.UUID,
        artifact: str | dict[str, Any] | list[Any],
        declared_type: EntityType | None,
    ) -> None:
        """Background flow: ENRICHING → extract → enrich each → COMPLETED."""
        try:
            async with self._db.session() as session:
                await self._lifecycle.transition(
                    session,
                    investigation_id,
                    InvestigationState.ENRICHING,
                    reason="extraction starting",
                )
                await session.commit()

            extracted = self._do_extract(artifact, declared_type)
            log.info(
                "ingest.extraction_done",
                investigation_id=str(investigation_id),
                count=len(extracted),
            )

            resolved_with_evidence: list[tuple[Any, uuid.UUID]] = []
            async with self._db.session() as session:
                for ioc in extracted:
                    resolved = await self._resolver.resolve(session, ioc.value, ioc.entity_type)
                    evidence = Evidence(
                        source="internal_extraction",
                        type=resolved.entity_type.value,
                        raw_data={"value": ioc.value, "extraction_method": ioc.extraction_method},
                        normalized_data={"canonical_form": resolved.canonical_form},
                        confidence=ioc.confidence,
                        provenance=Provenance(
                            level=ProvenanceLevel.PRIMARY_SOURCE,
                            source_reliability=0.95,
                            extraction_method=ioc.extraction_method,
                            chain_of_custody=[head_evidence_id],
                        ),
                        linked_entities=[resolved.entity_id],
                        investigation_id=investigation_id,
                    )
                    ev_id = await self._evidence.record(session, evidence)
                    await self._events.emit(
                        session,
                        EventType.IOC_EXTRACTED,
                        source="extraction",
                        investigation_id=investigation_id,
                        target=resolved.canonical_form,
                        evidence_refs=[ev_id, head_evidence_id],
                        metadata={
                            "entity_type": resolved.entity_type.value,
                            "extraction_method": ioc.extraction_method,
                        },
                        confidence=ioc.confidence,
                    )
                    resolved_with_evidence.append((resolved, ev_id))
                await session.commit()

            for resolved, ev_id in resolved_with_evidence:
                await self._enrichment.enrich(
                    resolved,
                    investigation_id=investigation_id,
                    ioc_evidence_id=ev_id,
                    chain_of_custody=[head_evidence_id, ev_id],
                )

            # --- Phase 3: CORRELATING phase ---------------------------
            # Materialize the deterministic state as a Neo4j subgraph,
            # then verify integrity. A clean report → COMPLETED; any
            # finding → REVIEW_REQUIRED (per CLAUDE.md invariant #6).
            async with self._db.session() as session:
                await self._lifecycle.transition(
                    session,
                    investigation_id,
                    InvestigationState.CORRELATING,
                    reason="graph correlation starting",
                )
                await session.commit()

            await self._correlator.correlate(investigation_id)
            report = await self._graph.integrity.check(investigation_id)

            if report.has_violations:
                async with self._db.session() as session:
                    await self._events.emit(
                        session,
                        EventType.INTEGRITY_VIOLATION_DETECTED,
                        source="graph_integrity",
                        investigation_id=investigation_id,
                        target=str(investigation_id),
                        metadata=report.to_dict(),
                        confidence=0.0,
                    )
                    await self._lifecycle.transition(
                        session,
                        investigation_id,
                        InvestigationState.REVIEW_REQUIRED,
                        reason="integrity violations detected",
                    )
                    await session.commit()
            else:
                async with self._db.session() as session:
                    await self._lifecycle.transition(
                        session,
                        investigation_id,
                        InvestigationState.COMPLETED,
                        reason="correlation + integrity clean",
                    )
                    await session.commit()
        except Exception as e:
            log.exception(
                "ingest.background_failed",
                investigation_id=str(investigation_id),
                error=str(e),
            )
            try:
                async with self._db.session() as session:
                    await self._lifecycle.transition(
                        session,
                        investigation_id,
                        InvestigationState.FAILED,
                        reason=f"background error: {type(e).__name__}",
                    )
                    await session.commit()
            except Exception:
                log.exception("ingest.failed_state_transition_also_failed")

    def _do_extract(
        self,
        artifact: str | dict[str, Any] | list[Any],
        declared_type: EntityType | None,
    ) -> list[ExtractedIOC]:
        if isinstance(artifact, str):
            if declared_type and declared_type in {
                EntityType.URL,
                EntityType.DOMAIN,
                EntityType.IP,
                EntityType.EMAIL,
                EntityType.HASH_MD5,
                EntityType.HASH_SHA1,
                EntityType.HASH_SHA256,
            }:
                # Caller asserts a specific type; normalize directly without regex scan.
                normalized = self._resolver.normalize(artifact, declared_type)
                return [
                    ExtractedIOC(
                        value=artifact,
                        canonical_form=normalized.canonical_form,
                        entity_type=normalized.entity_type,
                        extraction_method="declared",
                        confidence=0.95,
                        metadata={},
                    )
                ]
            return extract_iocs(artifact, resolver=self._resolver)
        return extract_iocs_from_json(artifact, resolver=self._resolver)


def _derive_title(artifact: str | dict | list) -> str:
    if isinstance(artifact, str):
        return artifact[:200]
    try:
        return json.dumps(artifact)[:200]
    except (TypeError, ValueError):
        return "ingested payload"
