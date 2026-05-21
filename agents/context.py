"""AgentExecutionContext — per-call bundle handed to ``BaseAgent.execute``.

A context carries:

- identifiers (workflow_run_id, agent_run_id, investigation_id, correlation_id)
- collaborators (db, redis, evidence_store, event_emitter, lifecycle_manager)
- the LLM client (real or stub, decided at startup by settings.has_api_key)
- the investigation-scoped memory + audit logger (None when the agent is
  pre-investigation, e.g. firewall analyze on a raw prompt)
- the retry policy, token budget, and circuit-breaker registry
- the agent's input payload (workflow-state slice, typed by each agent)

Contexts are built by the orchestration runtime — agents must not
construct their own.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.cache.redis import RedisClient
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.llm.client import LLMClient
from core.llm.budget import InvestigationTokenBudget
from evidence.store import EvidenceStore
from investigation.lifecycle.manager import LifecycleManager
from orchestration.memory.audit import MemoryAuditLogger
from orchestration.memory.store import InvestigationMemory
from orchestration.retry.circuit_breaker import CircuitBreakerRegistry
from orchestration.retry.policies import RetryPolicy


@dataclass(frozen=True)
class AgentExecutionContext:
    agent_run_id: uuid.UUID
    workflow_run_id: uuid.UUID
    node_name: str
    correlation_id: str | None
    investigation_id: uuid.UUID | None

    # Collaborators
    database: Database
    redis: RedisClient
    evidence_store: EvidenceStore
    event_emitter: EventEmitter
    lifecycle_manager: LifecycleManager
    llm: LLMClient

    # Per-investigation surfaces (None if no investigation yet bound).
    memory: InvestigationMemory | None
    memory_audit: MemoryAuditLogger | None
    token_budget: InvestigationTokenBudget | None

    # Reliability primitives
    retry_policy: RetryPolicy
    circuit_breakers: CircuitBreakerRegistry

    # Per-agent input slice — opaque to the runtime.
    inputs: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
