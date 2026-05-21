"""Workflow-detail router — Phase 5.

Single GET endpoint that returns the full audit view of a workflow run:
header + every agent run + their findings (structured, no raw text).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from apps.api.dependencies import OrchestrationServiceDep
from schemas.api.workflows import WorkflowDetailResponse

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get(
    "/{workflow_run_id}",
    response_model=WorkflowDetailResponse,
    summary="Workflow run detail (header + agent runs).",
)
async def get_workflow(
    workflow_run_id: uuid.UUID,
    orchestration: OrchestrationServiceDep,
) -> WorkflowDetailResponse:
    data = await orchestration.get_workflow(workflow_run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    return WorkflowDetailResponse(**data)
