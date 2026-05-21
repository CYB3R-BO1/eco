"""Phase 5 — Agent orchestration runtime.

The orchestration package wraps Phase 1–4 services as LangGraph nodes,
manages workflow lifecycle, provides bounded investigation memory, and
records every agent execution. It is the *only* place LangGraph is used.

Phase 1–4 services keep their public APIs; orchestration calls them
through those APIs and never reaches into their internals.
"""
from orchestration.service import OrchestrationService, WorkflowRunHandle

__all__ = ["OrchestrationService", "WorkflowRunHandle"]
