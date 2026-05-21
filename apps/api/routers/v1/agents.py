"""Agent orchestration router — Phase 5.

Two endpoints:

* ``POST /agents/run``           — start a workflow; 202 with run id.
* ``GET  /agents/status/{id}``   — current workflow-run status.

The actual workflow execution runs in the background (asyncio.task)
managed inside :class:`OrchestrationService` — the request returns 202
immediately. Callers poll status or fetch ``GET /workflows/{id}`` for
the full audit view once the run finishes.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from apps.api.dependencies import OrchestrationServiceDep
from schemas.api.agents import (
    AgentStatusResponse,
    RunWorkflowRequest,
    RunWorkflowResponse,
    WorkflowRunLinks,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "/run",
    response_model=RunWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an orchestration workflow.",
)
async def run_workflow(
    body: RunWorkflowRequest,
    orchestration: OrchestrationServiceDep,
) -> JSONResponse:
    try:
        handle = await orchestration.run_workflow(
            workflow_name=body.workflow,
            inputs=body.inputs,
            options=body.options.model_dump(exclude_none=True),
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = RunWorkflowResponse(
        workflow_run_id=handle.workflow_run_id,
        workflow_name=handle.workflow_name,
        status=handle.status.value,
        investigation_id=handle.investigation_id,
        idempotent_replay=handle.idempotent_replay,
        links=WorkflowRunLinks(
            status=f"/api/v1/agents/status/{handle.workflow_run_id}",
            workflow=f"/api/v1/workflows/{handle.workflow_run_id}",
        ),
    )
    code = status.HTTP_200_OK if handle.idempotent_replay else status.HTTP_202_ACCEPTED
    return JSONResponse(content=response.model_dump(mode="json"), status_code=code)


@router.get(
    "/status/{workflow_run_id}",
    response_model=AgentStatusResponse,
    summary="Get the current status of a workflow run.",
)
async def get_status(
    workflow_run_id: uuid.UUID,
    orchestration: OrchestrationServiceDep,
) -> AgentStatusResponse:
    data = await orchestration.get_agent_status(workflow_run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    return AgentStatusResponse(**data)
