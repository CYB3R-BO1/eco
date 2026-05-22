"""Investigation read endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from apps.api.dependencies import SessionDep
from apps.api.rbac import requires
from core.security.rbac import Permission
from schemas.api.graph import TimelinePageResponse
from schemas.api.investigation import InvestigationResponse, TimelineEntry
from storage.postgres.models.evidence import EvidenceRow
from storage.postgres.models.investigation import Investigation
from storage.postgres.models.investigation_event import InvestigationEvent

router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.get(
    "/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Fetch an investigation with its evidence and timeline",
    dependencies=[Depends(requires(Permission.INVESTIGATION_READ))],
)
async def get_investigation(
    investigation_id: uuid.UUID,
    session: SessionDep,
    timeline_limit: int = Query(default=100, ge=1, le=1000),
) -> InvestigationResponse:
    investigation = await session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="investigation not found")

    ev_stmt = (
        select(EvidenceRow.id)
        .where(EvidenceRow.investigation_id == investigation_id)
        .order_by(EvidenceRow.created_at.asc())
    )
    evidence_ids = [row[0] for row in (await session.execute(ev_stmt)).all()]

    tl_stmt = (
        select(InvestigationEvent)
        .where(InvestigationEvent.investigation_id == investigation_id)
        .order_by(InvestigationEvent.timestamp.asc())
        .limit(timeline_limit)
    )
    timeline_rows = (await session.execute(tl_stmt)).scalars().all()
    timeline = [
        TimelineEntry(
            event_id=row.id,
            event_type=row.event_type,
            timestamp=row.timestamp,
            source=row.source,
            actor=row.actor,
            target=row.target,
            evidence_refs=list(row.evidence_refs or []),
            confidence=row.confidence,
            event_metadata=row.event_metadata,
        )
        for row in timeline_rows
    ]

    return InvestigationResponse(
        id=investigation.id,
        title=investigation.title,
        status=investigation.status,
        severity=investigation.severity,
        summary=investigation.summary,
        confidence_score=investigation.confidence_score,
        schema_version=investigation.schema_version,
        created_at=investigation.created_at,
        updated_at=investigation.updated_at,
        evidence_refs=evidence_ids,
        timeline=timeline,
    )


@router.get(
    "/{investigation_id}/timeline",
    response_model=TimelinePageResponse,
    summary="Paginated chronological replay of investigation events",
    dependencies=[Depends(requires(Permission.INVESTIGATION_READ))],
)
async def get_investigation_timeline(
    investigation_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TimelinePageResponse:
    """Timeline is read from ``investigation_events`` (immutable, append-only).

    The graph holds the structural view; this endpoint holds the
    chronological one. They are intentionally separate per the
    deterministic / AI-narrative split in CLAUDE.md invariant #5.
    """
    inv_exists = await session.scalar(
        select(Investigation.id).where(Investigation.id == investigation_id)
    )
    if inv_exists is None:
        raise HTTPException(status_code=404, detail="investigation not found")

    stmt = (
        select(InvestigationEvent)
        .where(InvestigationEvent.investigation_id == investigation_id)
        .order_by(InvestigationEvent.timestamp.asc(), InvestigationEvent.id.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    events = [
        {
            "event_id": str(row.id),
            "event_type": row.event_type.value,
            "timestamp": row.timestamp.isoformat(),
            "source": row.source,
            "actor": row.actor,
            "target": row.target,
            "evidence_refs": [str(x) for x in (row.evidence_refs or [])],
            "confidence": row.confidence,
            "metadata": dict(row.event_metadata or {}),
        }
        for row in rows
    ]
    return TimelinePageResponse(
        investigation_id=investigation_id,
        events=events,
        limit=limit,
        offset=offset,
    )
