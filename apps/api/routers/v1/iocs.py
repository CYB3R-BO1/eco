"""IOC ingestion + extraction endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from apps.api.dependencies import (
    EntityResolutionDep,
    IngestionPipelineDep,
)
from apps.api.rbac import requires
from core.security.rbac import Permission
from investigation.extraction.extractor import (
    TooLargeError,
    TooManyIocsError,
    extract_iocs,
)
from investigation.extraction.json_walker import extract_iocs_from_json
from investigation.ingestion.validation import IngestValidationError
from schemas.api.ioc import (
    ExtractRequest,
    ExtractResponse,
    ExtractedIOCResponse,
    IngestRequest,
    IngestResponse,
)

router = APIRouter(prefix="/iocs", tags=["iocs"])


@router.post(
    "/extract",
    response_model=ExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="Stateless IOC extraction",
    description="Run regex extraction + normalization over a text or JSON payload. "
    "Does not create an investigation and does not persist anything.",
    dependencies=[Depends(requires(Permission.IOC_EXTRACT))],
)
async def extract_endpoint(
    body: ExtractRequest,
    resolver: EntityResolutionDep,
) -> ExtractResponse:
    if body.text is None and body.json_payload is None:
        raise HTTPException(status_code=400, detail="provide 'text' or 'json'")
    if body.text is not None and body.json_payload is not None:
        raise HTTPException(status_code=400, detail="provide exactly one of 'text' or 'json'")

    try:
        if body.text is not None:
            extracted = extract_iocs(body.text, types=body.types, resolver=resolver)
        else:
            extracted = extract_iocs_from_json(
                body.json_payload, types=body.types, resolver=resolver
            )
    except TooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except TooManyIocsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return ExtractResponse(
        extracted=[
            ExtractedIOCResponse(
                value=i.value,
                canonical_form=i.canonical_form,
                entity_type=i.entity_type,
                extraction_method=i.extraction_method,
                confidence=i.confidence,
                metadata=i.metadata,
            )
            for i in extracted
        ]
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest an artifact and start an investigation",
    description="Creates an Investigation, records the raw artifact as Evidence, "
    "and triggers background extraction + enrichment. Returns immediately.",
    dependencies=[Depends(requires(Permission.IOC_INGEST))],
)
async def ingest_endpoint(
    body: IngestRequest,
    pipeline: IngestionPipelineDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    try:
        result = await pipeline.ingest(
            artifact=body.artifact,
            declared_type=body.type,
            source_hint=body.source_hint,
            idempotency_key=idempotency_key,
        )
    except IngestValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return IngestResponse(
        investigation_id=result.investigation_id,
        status=result.status,
        evidence_id=result.evidence_id,
    )
