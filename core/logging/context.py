"""Thin wrappers around ``structlog.contextvars``.

Named constants keep context keys greppable. Every key bound here is
automatically merged into every log line for the duration of the request
(via the ``merge_contextvars`` processor configured in setup.py).

Phase 6 expands beyond Phase 1's ``correlation_id``: investigation /
workflow / agent / subject IDs are bound at their respective scopes so
downstream logs are auto-tagged without explicit ``log.bind(...)`` calls.
"""
from __future__ import annotations

import uuid
from typing import Any

from structlog.contextvars import bind_contextvars, clear_contextvars, unbind_contextvars

CORRELATION_ID = "correlation_id"
INVESTIGATION_ID = "investigation_id"
WORKFLOW_RUN_ID = "workflow_run_id"
AGENT_RUN_ID = "agent_run_id"
SUBJECT = "subject"


def bind(**context: Any) -> None:
    bind_contextvars(**context)


def unbind(*keys: str) -> None:
    unbind_contextvars(*keys)


def clear() -> None:
    clear_contextvars()


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def bind_correlation_id(value: str) -> None:
    bind_contextvars(**{CORRELATION_ID: value})


def bind_investigation(value: str | uuid.UUID) -> None:
    bind_contextvars(**{INVESTIGATION_ID: str(value)})


def bind_workflow_run(value: str | uuid.UUID) -> None:
    bind_contextvars(**{WORKFLOW_RUN_ID: str(value)})


def bind_agent_run(value: str | uuid.UUID) -> None:
    bind_contextvars(**{AGENT_RUN_ID: str(value)})


def bind_subject(value: str) -> None:
    """Bind the authenticated JWT subject (Phase 6 WP3)."""
    bind_contextvars(**{SUBJECT: value})


def unbind_investigation() -> None:
    unbind_contextvars(INVESTIGATION_ID)


def unbind_workflow_run() -> None:
    unbind_contextvars(WORKFLOW_RUN_ID)


def unbind_agent_run() -> None:
    unbind_contextvars(AGENT_RUN_ID)
