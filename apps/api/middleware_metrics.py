"""HTTP request metrics middleware.

Records ``http_requests_total`` and ``http_request_duration_seconds`` keyed
by the matched route TEMPLATE (e.g. ``/api/v1/investigations/{id}``) so the
label cardinality is bounded. Unmatched paths (404s) are bucketed under a
single ``unmatched`` label rather than each unique URL being its own bucket.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)


def _route_label(request: Request, response: Response | None) -> str:
    """Return the matched route template or ``unmatched``.

    Starlette sets ``request.scope["route"]`` once routing has resolved. We
    only consult the scope AFTER ``call_next`` to ensure the route has been
    matched. A missing route means no handler ran (404 / 405) — bucket those
    under one label so attackers can't blow up label cardinality by probing
    random URLs.
    """
    route = request.scope.get("route")
    if route is None:
        return "unmatched"
    # FastAPI APIRoute and Starlette Route both expose ``path``.
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "unmatched"


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = _route_label(request, response)
            status = str(response.status_code) if response is not None else "500"
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                route=route,
                status=status,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                route=route,
            ).observe(elapsed)
