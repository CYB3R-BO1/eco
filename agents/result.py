"""AgentResult — the structured return type of every agent.

Frozen dataclass. The runtime persists this verbatim to ``agent_runs``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.llm.tokens import AITokenUsage


class AgentRunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"


@dataclass(frozen=True)
class AgentResult:
    agent_run_id: uuid.UUID
    agent_name: str
    status: AgentRunStatus
    evidence_refs: list[uuid.UUID] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    error: str | None = None
    ai_tokens: AITokenUsage = field(default_factory=AITokenUsage)
    retries_used: int = 0
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == AgentRunStatus.SUCCESS

    @property
    def degraded(self) -> bool:
        return self.status in {
            AgentRunStatus.DEGRADED,
            AgentRunStatus.AI_UNAVAILABLE,
            AgentRunStatus.TIMEOUT,
        }

    @property
    def failed(self) -> bool:
        return self.status == AgentRunStatus.FAILED
