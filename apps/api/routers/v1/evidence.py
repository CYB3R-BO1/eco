"""Evidence read endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from apps.api.dependencies import EvidenceStoreDep, SessionDep
from schemas.api.evidence import EvidenceResponse, ProvenanceResponse

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get(
    "/{evidence_id}",
    response_model=EvidenceResponse,
    summary="Fetch a single Evidence record with full provenance",
)
async def get_evidence(
    evidence_id: uuid.UUID,
    session: SessionDep,
    store: EvidenceStoreDep,
) -> EvidenceResponse:
    evidence = await store.get(session, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="evidence not found")

    return EvidenceResponse(
        id=evidence.id,
        source=evidence.source,
        type=evidence.type,
        timestamp=evidence.timestamp,
        raw_data=evidence.raw_data,
        normalized_data=evidence.normalized_data,
        confidence=evidence.confidence,
        provenance=ProvenanceResponse(
            level=evidence.provenance.level,
            source_reliability=evidence.provenance.source_reliability,
            extraction_method=evidence.provenance.extraction_method,
            chain_of_custody=evidence.provenance.chain_of_custody,
        ),
        linked_entities=evidence.linked_entities,
        investigation_id=evidence.investigation_id,
    )
