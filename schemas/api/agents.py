"""Pydantic DTOs for ``/agents`` endpoints (Phase 5).

Request:
- :class:`RunWorkflowRequest` — start a workflow.

Response:
- :class:`RunWorkflowResponse` — 202 ACK with workflow_run_id.
- :class:`AgentStatusResponse` — current workflow-run status + last node.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


WorkflowNameLiteral = Literal["investigation", "firewall"]


class RunWorkflowOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_reasoning: bool = True
    ai_budget_tokens: int | None = Field(default=None, ge=0, le=200_000)


class RunWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowNameLiteral
    inputs: dict[str, Any]
    options: RunWorkflowOptions = Field(default_factory=RunWorkflowOptions)
    idempotency_key: str | None = Field(default=None, max_length=128)


class WorkflowRunLinks(BaseModel):
    status: str
    workflow: str


class RunWorkflowResponse(BaseModel):
    workflow_run_id: uuid.UUID
    workflow_name: str
    status: str
    investigation_id: uuid.UUID | None = None
    idempotent_replay: bool = False
    links: WorkflowRunLinks


class AgentStatusResponse(BaseModel):
    workflow_run_id: uuid.UUID
    workflow_name: str
    status: str
    investigation_id: uuid.UUID | None = None
    correlation_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    degraded: bool = False
    ai_tokens_input: int = 0
    ai_tokens_output: int = 0
    last_node: str | None = None
    error: str | None = None
    actor: str
