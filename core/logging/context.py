"""Thin wrappers around ``structlog.contextvars``.

Callers shouldn't import structlog internals directly; new context keys
(``investigation_id``, ``workflow_id``, ``agent_id``) added in later phases
live here as named constants so they're greppable.
"""
from __future__ import annotations

import uuid
from typing import Any

from structlog.contextvars import bind_contextvars, clear_contextvars, unbind_contextvars

CORRELATION_ID = "correlation_id"


def bind(**context: Any) -> None:
    bind_contextvars(**context)


def unbind(*keys: str) -> None:
    unbind_contextvars(*keys)


def clear() -> None:
    clear_contextvars()


def new_correlation_id() -> str:
    return str(uuid.uuid4())
