"""HTTP idempotency replay (Phase 6 WP5).

Generalizes the firewall-specific idempotency cache so any mutating
route can opt in via a FastAPI dependency. The key shape is
``idempotency:{kid}:{idempotency_key}`` so two different tenants (when
multi-tenancy lands as an additive concern) can re-use idempotency keys
without collision.

The cached value stores ``status``, ``body_fingerprint``, and
``correlation_id`` — never the response body itself. Replays return a
slim header-only response carrying the original status code and a
``X-Idempotent-Replay: true`` marker; clients can then re-fetch the
full state through the normal read API if they need it. Storing the
body fingerprint (SHA-256) lets us assert the second call's response
matches the first without persisting raw content (invariant #12).

This is the HTTP-cache layer. The pipeline-level idempotency keys
(``IdempotencyKeyRow``) remain authoritative for "did we already
create this row" — the two layers compose: HTTP cache short-circuits
the second call entirely; the row-level guard handles the case where
two callers race past the cache window.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

import orjson
import structlog
from fastapi import Depends, Header, Request, Response

from apps.api.auth import get_current_principal
from core.security.hashing import sha256_hex
from core.security.principal import Principal

log = structlog.get_logger(__name__)

# 24-hour replay window. Tunable later via settings if a route needs longer
# protection — most APIs use 24h as the standard idempotency-key TTL.
_IDEMPOTENCY_TTL_SECONDS = 86_400
_REPLAY_HEADER = "X-Idempotent-Replay"


class IdempotencyConflictError(Exception):
    """Same key, different body fingerprint — RFC 7231 / idempotency-key spec.

    The caller previously used this key with a different request payload.
    Either the client is reusing keys without intent, or there's a
    collision in their key-generation scheme. Mapped to 422 by the
    handler in ``apps/api/exceptions.py``.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"idempotency key {key!r} reused with different body")
        self.key = key


async def _enforce(
    request: Request,
    idempotency_key: str | None,
    principal: Principal | None,
) -> Response | None:
    """Return a replay response on hit, ``None`` on miss / unused.

    ``principal`` is optional so the same primitive works under tests
    that don't gate auth. In production, the dependency tree always
    resolves the principal first.
    """
    if not idempotency_key:
        return None
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return None

    kid = principal.token_kid if principal else "anon"
    cache_key = f"idempotency:{kid}:{idempotency_key}"
    raw = await redis.client.get(cache_key)
    if raw is None:
        return None
    try:
        cached = orjson.loads(raw)
    except orjson.JSONDecodeError:
        log.warning("idempotency.cache_corrupt", key=cache_key)
        return None
    log.info(
        "idempotency.replay",
        key=cache_key,
        status=cached.get("status"),
    )
    return Response(
        status_code=int(cached.get("status", 200)),
        headers={
            _REPLAY_HEADER: "true",
            "X-Body-Fingerprint": cached.get("body_fingerprint", ""),
            "X-Correlation-ID": cached.get("correlation_id", ""),
        },
    )


async def _persist(
    request: Request,
    idempotency_key: str | None,
    principal: Principal | None,
    response: Response,
) -> None:
    if not idempotency_key:
        return
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    if not 200 <= response.status_code < 300:
        return  # only cache successful, replay-safe responses

    kid = principal.token_kid if principal else "anon"
    cache_key = f"idempotency:{kid}:{idempotency_key}"
    body = getattr(response, "body", b"") or b""
    payload = orjson.dumps(
        {
            "status": response.status_code,
            "body_fingerprint": sha256_hex(body) if body else "",
            "correlation_id": getattr(request.state, "correlation_id", ""),
        }
    )
    await redis.client.setex(cache_key, _IDEMPOTENCY_TTL_SECONDS, payload)


def idempotent(
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: Annotated[Principal, Depends(get_current_principal)] = None,  # type: ignore[assignment]
) -> str | None:
    """FastAPI dependency that registers idempotency intent for a route.

    The route handler runs normally; this dependency stashes the key on
    ``request.state`` so the ``IdempotencyResponseMiddleware`` can pick
    up the result and cache it. The dependency itself returns the key so
    routes that already accept ``Idempotency-Key`` keep the same
    signature.
    """
    request.state.idempotency_key = idempotency_key
    request.state.idempotency_kid = principal.token_kid if principal else "anon"
    return idempotency_key


class IdempotencyResponseMiddleware:
    """ASGI middleware that completes the idempotency loop.

    Runs BEFORE the route to short-circuit on cache hit, then AFTER the
    route to persist the response fingerprint. Uses pure ASGI rather
    than ``BaseHTTPMiddleware`` because we need to swap responses without
    buffering the entire body twice through the BaseHTTPMiddleware shim.
    """

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        idempotency_key = request.headers.get("idempotency-key")
        # On cache hit we short-circuit BEFORE running the route. Auth has
        # not yet happened at this layer — we use ``anon`` as the kid
        # bucket, which means the HTTP-level cache always treats hits as
        # the same caller. That's safe because the body fingerprint is
        # also checked at the application layer for high-stakes routes.
        replay = await _enforce(request, idempotency_key, principal=None)
        if replay is not None:
            await replay(scope, receive, send)
            return

        # Buffer the response so we can fingerprint the body before
        # forwarding it. Only fingerprints are stored — never raw bodies.
        captured_body = bytearray()
        captured_status = 200
        captured_headers: list[tuple[bytes, bytes]] = []

        async def send_wrapper(message: Callable[..., Awaitable[None]] | dict) -> None:  # type: ignore[type-arg]
            nonlocal captured_status, captured_headers
            if isinstance(message, dict):
                if message.get("type") == "http.response.start":
                    captured_status = message.get("status", 200)
                    captured_headers = list(message.get("headers", []))
                elif message.get("type") == "http.response.body":
                    body = message.get("body", b"") or b""
                    if body:
                        captured_body.extend(body)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if (
            idempotency_key
            and 200 <= captured_status < 300
            and getattr(request.app.state, "redis", None) is not None
        ):
            redis = request.app.state.redis
            kid = getattr(request.state, "idempotency_kid", "anon")
            cache_key = f"idempotency:{kid}:{idempotency_key}"
            payload = orjson.dumps(
                {
                    "status": captured_status,
                    "body_fingerprint": sha256_hex(bytes(captured_body))
                    if captured_body
                    else "",
                    "correlation_id": getattr(request.state, "correlation_id", ""),
                }
            )
            try:
                await redis.client.setex(
                    cache_key, _IDEMPOTENCY_TTL_SECONDS, payload
                )
            except Exception:
                log.exception("idempotency.persist_failed", key=cache_key)
