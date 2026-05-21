"""LangGraph orchestration runtime.

Public surface:

- :class:`WorkflowState` — typed dict shared across graph nodes.
- :class:`WorkflowGraphBuilder` — builds :class:`StateGraph` instances for
  named workflows.
- :func:`build_checkpointer` — returns an :class:`AsyncPostgresSaver` when
  ``langgraph-checkpoint-postgres`` is installed; otherwise falls back to
  in-memory (acceptable for unit tests and dev — durability requires the
  postgres package).
- :class:`WorkflowTracer` — OpenTelemetry span helper for nodes.
"""
from orchestration.runtime.checkpointer import (
    CheckpointerKind,
    build_checkpointer,
    setup_checkpointer,
)
from orchestration.runtime.state import (
    WorkflowError,
    WorkflowState,
    new_workflow_state,
    record_agent_result,
    record_error,
)
from orchestration.runtime.tracer import WorkflowTracer

__all__ = [
    "CheckpointerKind",
    "WorkflowError",
    "WorkflowState",
    "WorkflowTracer",
    "build_checkpointer",
    "new_workflow_state",
    "record_agent_result",
    "record_error",
    "setup_checkpointer",
]
