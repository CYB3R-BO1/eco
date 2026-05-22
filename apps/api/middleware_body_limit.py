"""Hard cap on request body size (Phase 6 WP5).

Independent of the firewall's prompt-size caps. This middleware rejects
oversized payloads BEFORE the route handler runs so a 100 MB POST can't
chew up memory just to be rejected at the schema layer.

Two enforcement layers:

1. If ``Content-Length`` is present and over the limit → 413 immediately.
2. If it's missing (chunked transfer-encoding), wrap the receive() ASGI
   callable so it short-circuits as soon as the running byte count
   exceeds the limit. We can't trust the upstream to send a
   ``Content-Length`` so the byte-counting wrapper is the real guard.

Honors ``Content-Length: 0`` and missing-with-empty-body.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class MaxBodyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                return _too_large(self._max_bytes)
            if declared > self._max_bytes:
                return _too_large(self._max_bytes)
            return await call_next(request)

        # No Content-Length — wrap receive() and count bytes as they arrive.
        original_receive = request.receive
        seen = 0
        limit = self._max_bytes

        async def counting_receive() -> dict:  # type: ignore[type-arg]
            nonlocal seen
            message = await original_receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if body:
                    seen += len(body)
                if seen > limit:
                    # ASGI doesn't let us return a response from receive(),
                    # so we mark and let the route handler exit with a 413.
                    # The most reliable way is to raise — Starlette translates
                    # it. But to keep the contract clean we surface a 413
                    # by truncating the body and setting an error flag the
                    # next call_next can't disambiguate. Simpler: raise.
                    raise _BodyTooLargeError(limit)
            return message

        request._receive = counting_receive  # type: ignore[attr-defined]
        try:
            return await call_next(request)
        except _BodyTooLargeError:
            return _too_large(self._max_bytes)


class _BodyTooLargeError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"request body exceeded {limit} bytes")
        self.limit = limit


def _too_large(limit: int) -> Response:
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": 413,
                "message": f"request body exceeds {limit} bytes",
            }
        },
    )
