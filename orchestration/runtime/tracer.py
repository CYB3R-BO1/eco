"""WorkflowTracer — one OpenTelemetry span per node execution.

Spans carry attributes: ``workflow_run_id``, ``investigation_id``,
``node_name``, ``agent_name`` (when applicable), ``status``,
``duration_ms``. The tracer is a thin facade; we use the global tracer
provider configured at app startup so spans flow into whatever exporter
the platform has wired up.

The tracer never logs raw prompt/completion text — only fingerprints if
the caller passes one.

Phase 6 (WP2): each ``node_span`` also observes a duration histogram so
operators can build dashboards/alerts without an OTel backend.
"""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Iterator

import structlog
from opentelemetry import trace

from core.observability.metrics import (
    AGENT_RUN_DURATION_SECONDS,
    WORKFLOW_DURATION_SECONDS,
)

log = structlog.get_logger(__name__)


class WorkflowTracer:
    def __init__(self, service_name: str = "orchestration") -> None:
        self._tracer = trace.get_tracer(service_name)

    @contextmanager
    def node_span(
        self,
        *,
        workflow_run_id: uuid.UUID,
        node_name: str,
        agent_name: str | None = None,
        investigation_id: uuid.UUID | None = None,
    ) -> Iterator[trace.Span]:
        start = time.perf_counter()
        with self._tracer.start_as_current_span(
            name=f"orchestration.node.{node_name}",
            attributes={
                "workflow.run_id": str(workflow_run_id),
                "workflow.node": node_name,
                "workflow.agent": agent_name or "",
                "workflow.investigation_id": str(investigation_id) if investigation_id else "",
            },
        ) as span:
            try:
                yield span
            finally:
                if agent_name:
                    outcome = "ok"
                    status_attr = span.attributes.get("workflow.outcome") if hasattr(span, "attributes") else None
                    if isinstance(status_attr, str) and status_attr:
                        outcome = status_attr
                    AGENT_RUN_DURATION_SECONDS.labels(
                        agent_name=agent_name,
                        outcome=outcome,
                    ).observe(time.perf_counter() - start)

    @contextmanager
    def workflow_span(
        self,
        *,
        workflow_run_id: uuid.UUID,
        workflow_name: str,
        investigation_id: uuid.UUID | None = None,
    ) -> Iterator[trace.Span]:
        """Top-level span for a workflow run. Emits ``WORKFLOW_DURATION_SECONDS``."""
        start = time.perf_counter()
        terminal_state = "unknown"
        with self._tracer.start_as_current_span(
            name=f"orchestration.workflow.{workflow_name}",
            attributes={
                "workflow.run_id": str(workflow_run_id),
                "workflow.name": workflow_name,
                "workflow.investigation_id": str(investigation_id) if investigation_id else "",
            },
        ) as span:
            try:
                yield span
                # Caller may attach `workflow.terminal_state` via set_attribute.
                if hasattr(span, "attributes"):
                    ts = span.attributes.get("workflow.terminal_state")
                    if isinstance(ts, str) and ts:
                        terminal_state = ts
            finally:
                WORKFLOW_DURATION_SECONDS.labels(
                    workflow_name=workflow_name,
                    terminal_state=terminal_state,
                ).observe(time.perf_counter() - start)
