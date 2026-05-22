"""Security response headers (Phase 6 WP5).

Defense-in-depth HTTP headers applied to every response. Defaults match
OWASP's secure-headers guidance:

- ``Strict-Transport-Security``: only in production. Adding it locally
  would force HTTPS on ``localhost`` and break dev workflows.
- ``Content-Security-Policy``: ``default-src 'none'`` — this is a backend
  API; it returns JSON, never HTML. Locking the policy down eliminates
  XSS by construction.
- ``X-Frame-Options: DENY`` — no framing of any response. Combined with
  CSP this is belt-and-braces.
- ``X-Content-Type-Options: nosniff`` — block MIME sniffing in browsers
  that ignore our explicit ``Content-Type``.
- ``Referrer-Policy: no-referrer`` — never leak the request URL to
  cross-origin destinations.
- ``Permissions-Policy``: deny every powerful browser API. Same logic
  as CSP: this is an API, no UI surface.

CORS handling stays where it is (``CORSMiddleware`` in ``main.py``);
that's a request-side concern. This middleware only writes response
headers.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)
_HSTS_VALUE = "max-age=31536000; includeSubDomains"


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, is_production: bool) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        h.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
        if self._is_production:
            h.setdefault("Strict-Transport-Security", _HSTS_VALUE)
        return response
