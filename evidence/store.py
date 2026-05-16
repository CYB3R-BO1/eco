"""Write-once Evidence persistence.

This class is the ONLY allowed writer to the ``evidence`` table. It exposes
``record`` (INSERT) and read methods — no ``update`` and no ``delete``.
That's enforced by the public surface area, not by some database trigger;
code review and grep are the enforcement mechanism.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evidence.models import Evidence, Provenance
from evidence.provenance import ProvenanceLevel
from evidence.validation import validate
from storage.postgres.models.evidence import EvidenceRow

log = structlog.get_logger(__name__)


class EvidenceStore:
    """Stateless service. All operations take an AsyncSession."""

    async def record(self, session: AsyncSession, evidence: Evidence) -> uuid.UUID:
        validate(evidence)
        row = EvidenceRow(
            id=evidence.id,
            source=evidence.source,
            type=evidence.type,
            timestamp=evidence.timestamp,
            raw_data=evidence.raw_data,
            normalized_data=evidence.normalized_data,
            confidence=evidence.confidence,
            provenance=evidence.provenance.model_dump(mode="json"),
            linked_entities=evidence.linked_entities,
            investigation_id=evidence.investigation_id,
            created_at=evidence.timestamp,
        )
        session.add(row)
        await session.flush()
        log.info(
            "evidence.recorded",
            evidence_id=str(evidence.id),
            source=evidence.source,
            type=evidence.type,
            provenance_level=evidence.provenance.level.value,
        )
        return evidence.id

    async def get(self, session: AsyncSession, evidence_id: uuid.UUID) -> Evidence | None:
        row = await session.get(EvidenceRow, evidence_id)
        if row is None:
            return None
        return _row_to_domain(row)

    async def list_by_investigation(
        self, session: AsyncSession, investigation_id: uuid.UUID
    ) -> list[Evidence]:
        result = await session.execute(
            select(EvidenceRow)
            .where(EvidenceRow.investigation_id == investigation_id)
            .order_by(EvidenceRow.timestamp.asc())
        )
        return [_row_to_domain(r) for r in result.scalars().all()]


def _row_to_domain(row: EvidenceRow) -> Evidence:
    return Evidence(
        id=row.id,
        source=row.source,
        type=row.type,
        timestamp=row.timestamp,
        raw_data=row.raw_data,
        normalized_data=row.normalized_data,
        confidence=row.confidence,
        provenance=Provenance(
            level=ProvenanceLevel(row.provenance["level"]),
            source_reliability=row.provenance["source_reliability"],
            extraction_method=row.provenance["extraction_method"],
            chain_of_custody=[
                uuid.UUID(x) if isinstance(x, str) else x
                for x in row.provenance.get("chain_of_custody", [])
            ],
        ),
        linked_entities=list(row.linked_entities or []),
        investigation_id=row.investigation_id,
    )
