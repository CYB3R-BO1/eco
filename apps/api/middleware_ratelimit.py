"""Distributed rate limiting (Phase 6 WP5).

``slowapi`` with a Redis backend so limits are enforced across uvicorn
workers (in-process limits would be per-worker which is approximately
useless under load). Limit keys prefer the authenticated JWT subject
(via the ``Principal`` already bound to ``request.state``) and fall back
to the client IP for unauthenticated requests like ``/health``.

The limiter is constructed in ``main.py`` so the active settings (Redis
URL, default limit) are injected at create-app time. ``slowapi`` is
imported lazily — if the optional package is unavailable in a test
environment, ``build_limiter`` returns ``None`` and rate limiting is
effectively disabled. Production deployments install ``slowapi`` and
get the real limiter.
"""
from __future__ import annotations

from typing import Any

from starlette.requests import Request

from core.config.settings import Settings


def _request_key(request: Request) -> str:
    """Per-caller rate-limit key.

    Prefers the authenticated principal's subject so two distinct users
    behind the same NAT each get their own budget. Falls back to the
    client IP for unauthenticated endpoints (``/health``, ``/live``).
    """
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        subject = getattr(principal, "subject", None)
        if subject:
            return f"sub:{subject}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def build_limiter(settings: Settings) -> Any | None:
    """Return a configured ``slowapi.Limiter`` or ``None`` if unavailable.

    Returning ``None`` keeps the no-op path explicit at the call site —
    ``main.py`` checks the return value before wiring middleware.
    """
    try:
        from slowapi import Limiter  # type: ignore[import-not-found]
    except ImportError:
        return None

    return Limiter(
        key_func=_request_key,
        storage_uri=settings.redis.url,
        default_limits=[settings.security.rate_limit_default],
        strategy="moving-window",
        headers_enabled=True,
    )
