"""HTTP middleware: correlation IDs and request logging."""
from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars

CORRELATION_HEADER = "X-Correlation-ID"

log = structlog.get_logger("http")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request.

    Reads ``X-Correlation-ID`` from the incoming request or generates a UUID4,
    binds it to structlog's contextvars so every log line emitted during the
    request carries it, and echoes the header on the response so clients can
    pin server-side activity to their request.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        clear_contextvars()
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
