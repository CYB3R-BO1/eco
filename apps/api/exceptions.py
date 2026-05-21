"""Centralized exception handlers.

All handlers emit a uniform error envelope::

    {"error": {"code": <int>, "message": <str>, "details"?: <list|dict>}}

4xx logs at ``warning``; the catch-all 500 logs at ``exception`` with stack
info. The catch-all exists so unhandled errors never leak stack traces to
clients — they live only in logs.

Phase 2 also maps the domain exceptions raised by the IOC pipeline
(``InvalidTransitionError``, ``IngestValidationError``,
``EvidenceValidationError``) onto the same envelope.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from evidence.validation import EvidenceValidationError
from firewall.service import FirewallTimeoutError, PromptTooLargeError
from graph.governance.validator import (
    GraphSchemaViolationError,
    TraversalLimitExceededError,
)
from graph.graph_service.mutations import GraphCardinalityError
from graph.graph_service.traversal import NodeNotFoundError
from investigation.extraction.extractor import TooLargeError, TooManyIocsError
from investigation.ingestion.validation import IngestValidationError
from investigation.lifecycle.manager import InvalidTransitionError

log = structlog.get_logger("exception")


class WorkflowTimeoutError(Exception):
    """Raised when a workflow exceeds ``orchestration.workflow_timeout_seconds``."""

    def __init__(self, workflow_run_id: str, elapsed_seconds: float) -> None:
        self.workflow_run_id = workflow_run_id
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"workflow {workflow_run_id} timed out after {elapsed_seconds:.1f}s"
        )


class TokenBudgetExceededError(Exception):
    """Raised when an LLM call would breach the per-investigation token budget."""

    def __init__(self, investigation_id: str, requested: int, remaining: int) -> None:
        self.investigation_id = investigation_id
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"token budget exceeded for investigation {investigation_id}: "
            f"requested={requested} remaining={remaining}"
        )


class AgentExecutionError(Exception):
    """Raised when an agent run fails irrecoverably (after retries)."""

    def __init__(self, agent_name: str, reason: str) -> None:
        self.agent_name = agent_name
        self.reason = reason
        super().__init__(f"agent {agent_name} failed: {reason}")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        log.warning(
            "http_exception",
            status=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        log.warning("validation_error", errors=exc.errors(), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": 422,
                    "message": "validation_error",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(IngestValidationError)
    async def ingest_validation_handler(
        request: Request, exc: IngestValidationError
    ) -> JSONResponse:
        log.warning("ingest_validation_error", message=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": 400, "message": str(exc)}},
        )

    @app.exception_handler(EvidenceValidationError)
    async def evidence_validation_handler(
        request: Request, exc: EvidenceValidationError
    ) -> JSONResponse:
        log.warning("evidence_validation_error", message=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": 422, "message": str(exc)}},
        )

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition_handler(
        request: Request, exc: InvalidTransitionError
    ) -> JSONResponse:
        log.warning(
            "invalid_transition",
            current=exc.current.value,
            target=exc.target.value,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": 409, "message": str(exc)}},
        )

    @app.exception_handler(TooLargeError)
    async def too_large_handler(request: Request, exc: TooLargeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"error": {"code": 413, "message": str(exc)}},
        )

    @app.exception_handler(TooManyIocsError)
    async def too_many_handler(request: Request, exc: TooManyIocsError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": 422, "message": str(exc)}},
        )

    @app.exception_handler(GraphSchemaViolationError)
    async def graph_schema_violation_handler(
        request: Request, exc: GraphSchemaViolationError
    ) -> JSONResponse:
        log.warning(
            "graph_schema_violation",
            source=exc.source.value,
            rel=exc.rel.value,
            target=exc.target.value,
            reason=exc.reason,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": 409, "message": str(exc)}},
        )

    @app.exception_handler(GraphCardinalityError)
    async def graph_cardinality_handler(
        request: Request, exc: GraphCardinalityError
    ) -> JSONResponse:
        log.warning(
            "graph_cardinality_exceeded",
            source_id=str(exc.source_id),
            rel=exc.rel_type.value,
            count=exc.count,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": 409, "message": str(exc)}},
        )

    @app.exception_handler(NodeNotFoundError)
    async def node_not_found_handler(
        request: Request, exc: NodeNotFoundError
    ) -> JSONResponse:
        log.warning("graph_node_not_found", node_id=str(exc.node_id), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": 404, "message": str(exc)}},
        )

    @app.exception_handler(TraversalLimitExceededError)
    async def traversal_limit_handler(
        request: Request, exc: TraversalLimitExceededError
    ) -> JSONResponse:
        log.warning(
            "traversal_limit_exceeded",
            requested=exc.requested,
            maximum=exc.maximum,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": 422, "message": str(exc)}},
        )

    @app.exception_handler(PromptTooLargeError)
    async def prompt_too_large_handler(
        request: Request, exc: PromptTooLargeError
    ) -> JSONResponse:
        log.warning(
            "firewall.prompt_too_large",
            kind=exc.kind,
            length=exc.length,
            limit=exc.limit,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"error": {"code": 413, "message": str(exc)}},
        )

    @app.exception_handler(FirewallTimeoutError)
    async def firewall_timeout_handler(
        request: Request, exc: FirewallTimeoutError
    ) -> JSONResponse:
        log.warning("firewall.timeout", path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"error": {"code": 504, "message": str(exc) or "firewall analysis timed out"}},
        )

    @app.exception_handler(WorkflowTimeoutError)
    async def workflow_timeout_handler(
        request: Request, exc: WorkflowTimeoutError
    ) -> JSONResponse:
        log.warning(
            "workflow.timeout",
            workflow_run_id=exc.workflow_run_id,
            elapsed_seconds=exc.elapsed_seconds,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"error": {"code": 504, "message": str(exc)}},
        )

    @app.exception_handler(TokenBudgetExceededError)
    async def token_budget_handler(
        request: Request, exc: TokenBudgetExceededError
    ) -> JSONResponse:
        log.warning(
            "llm.token_budget_exceeded",
            investigation_id=exc.investigation_id,
            requested=exc.requested,
            remaining=exc.remaining,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": {"code": 429, "message": str(exc)}},
        )

    @app.exception_handler(AgentExecutionError)
    async def agent_execution_handler(
        request: Request, exc: AgentExecutionError
    ) -> JSONResponse:
        log.warning(
            "agent.execution_failed",
            agent_name=exc.agent_name,
            reason=exc.reason,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": 500, "message": str(exc)}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": 500, "message": "internal_server_error"}},
        )
