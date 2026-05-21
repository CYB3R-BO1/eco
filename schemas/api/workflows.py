"""Pydantic DTOs for ``GET /workflows/{id}`` — the auditor view.

Returns the workflow run header + every agent run + their findings
(structured, no raw text).
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class AgentRunDTO(BaseModel):
    agent_run_id: uuid.UUID
    agent_name: str
    node_name: str
    investigation_id: uuid.UUID | None = None
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    confidence: float | None = None
    retries_used: int = 0
    ai_tokens_input: int = 0
    ai_tokens_output: int = 0
    evidence_refs: list[uuid.UUID] = []
    findings_summary: dict[str, Any] = {}
    error: str | None = None


class WorkflowDetailResponse(BaseModel):
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
    agent_runs: list[AgentRunDTO]
