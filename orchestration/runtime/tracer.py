"""WorkflowTracer — one OpenTelemetry span per node execution.

Spans carry attributes: ``workflow_run_id``, ``investigation_id``,
``node_name``, ``agent_name`` (when applicable), ``status``,
``duration_ms``. The tracer is a thin facade; we use the global tracer
provider configured at app startup so spans flow into whatever exporter
the platform has wired up.

The tracer never logs raw prompt/completion text — only fingerprints if
the caller passes one.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

import structlog
from opentelemetry import trace

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
        with self._tracer.start_as_current_span(
            name=f"orchestration.node.{node_name}",
            attributes={
                "workflow.run_id": str(workflow_run_id),
                "workflow.node": node_name,
                "workflow.agent": agent_name or "",
                "workflow.investigation_id": str(investigation_id) if investigation_id else "",
            },
        ) as span:
            yield span
