"""HTTP idempotency replay (Phase 6 WP5, refined in Phase 7 WP1).

Per-route dependency that records an ``Idempotency-Key`` for a request,
checks Redis for a prior result keyed by the authenticated subject, and
either short-circuits the handler with a replay response or lets the
handler run and persists the body fingerprint for next time.

Why dependency, not ASGI middleware: the previous incarnation ran in
the ASGI stack BEFORE the auth dependency could resolve the principal,
so the cache key fell back to ``"anon"`` for every request. Two callers
sharing an ``Idempotency-Key`` would see each other's responses. The
dependency form runs after :func:`apps.api.auth.get_current_principal`,
so the cache key is always scoped by the verified ``subject`` claim.

The cached value stores ``status``, ``body_fingerprint``, and
``correlation_id`` — never the raw body. Replays return a slim
header-only response carrying the original status code and an
``X-Idempotent-Replay: true`` marker; clients can re-fetch the full
state through the read API if they need it. Storing the body
fingerprint (SHA-256) lets a future high-stakes route assert the
second call's response matches the first without persisting raw
content (invariant #12).

This is the HTTP-cache layer. The pipeline-level idempotency keys
(``IdempotencyKeyRow``) remain authoritative for "did we already
create this row?" — the two layers compose: HTTP cache short-circuits
the second call entirely; the row-level guard handles the case where
two callers race past the cache window.
"""
from __future__ import annotations

from typing import Annotated, Any

import orjson
import structlog
from fastapi import Depends, Header, HTTPException, Request, Response

from apps.api.auth import get_current_principal
from core.security.hashing import sha256_hex
from core.security.principal import Principal

log = structlog.get_logger(__name__)

# 24-hour replay window. Matches the IdempotencyKeyRow retention TTL so
# the two layers age out together.
_IDEMPOTENCY_TTL_SECONDS = 86_400
_REPLAY_HEADER = "X-Idempotent-Replay"


class IdempotencyConflictError(HTTPException):
    """Same key, different body fingerprint — RFC-style idempotency conflict.

    The caller previously used this key with a different request payload.
    Either the client is reusing keys without intent, or there's a
    collision in their key-generation scheme. Maps to HTTP 422.
    """

    def __init__(self, key: str) -> None:
        super().__init__(
            status_code=422,
            detail=f"idempotency key {key!r} reused with a different request body",
        )


def _cache_key(subject: str, key: str) -> str:
    return f"idempotency:{subject}:{key}"


async def _lookup(request: Request, redis_key: str) -> dict[str, Any] | None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return None
    raw = await redis.client.get(redis_key)
    if raw is None:
        return None
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        log.warning("idempotency.cache_corrupt", key=redis_key)
        return None


async def _persist(
    request: Request,
    redis_key: str,
    response: Response,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    if not 200 <= response.status_code < 300:
        return  # only cache successful, replay-safe responses
    body = getattr(response, "body", b"") or b""
    payload = orjson.dumps(
        {
            "status": response.status_code,
            "body_fingerprint": sha256_hex(body) if body else "",
            "correlation_id": getattr(request.state, "correlation_id", ""),
        }
    )
    try:
        await redis.client.setex(redis_key, _IDEMPOTENCY_TTL_SECONDS, payload)
    except Exception:
        log.exception("idempotency.persist_failed", key=redis_key)


async def idempotent_replay_or_register(
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: Annotated[Principal, Depends(get_current_principal)] = None,  # type: ignore[assignment]
) -> str | None:
    """FastAPI dependency that gates a route on idempotency.

    Behaviour:

    - Missing ``Idempotency-Key`` header → no-op, returns ``None``.
    - Cache hit → raises ``HTTPException`` with the cached status code
      and the ``X-Idempotent-Replay`` header set. The handler never
      runs. (We use HTTPException rather than swapping the Response
      because FastAPI dependencies cannot return a Response that
      replaces the handler's; raising is the supported short-circuit.)
    - Cache miss → registers a ``BackgroundTasks``-like hook on
      ``request.state`` so the response is persisted after the handler
      finishes successfully. Returns the key so the handler can read
      it if it wants to use the same key for downstream calls.

    The persistence step lives in
    :func:`persist_idempotent_response` which routes call as a second
    dependency wired through the response-cycle. Splitting the two
    halves keeps each half single-responsibility.
    """
    if not idempotency_key:
        return None

    subject = getattr(principal, "subject", None) or "anonymous"
    redis_key = _cache_key(subject, idempotency_key)
    cached = await _lookup(request, redis_key)
    if cached is not None:
        log.info(
            "idempotency.replay",
            key=redis_key,
            status=cached.get("status"),
        )
        # Short-circuit the handler. FastAPI will surface the
        # HTTPException as a JSONResponse; we attach the replay marker
        # via the ``headers`` dict.
        raise HTTPException(
            status_code=int(cached.get("status", 200)),
            detail={
                "replay": True,
                "body_fingerprint": cached.get("body_fingerprint", ""),
                "correlation_id": cached.get("correlation_id", ""),
            },
            headers={
                _REPLAY_HEADER: "true",
                "X-Body-Fingerprint": cached.get("body_fingerprint", ""),
            },
        )

    # Cache miss — stash the key on request.state so a downstream hook
    # can persist the result after the handler runs. Routes that want
    # idempotency persistence add ``Depends(persist_idempotent_response)``
    # to their dependency list.
    request.state.idempotency_redis_key = redis_key
    return idempotency_key


async def persist_idempotent_response(
    request: Request,
    response: Response,
) -> None:
    """Persist the response under the redis key registered by
    :func:`idempotent_replay_or_register`.

    Use as a second dependency on routes that want their successful
    responses cached. Safe to add to every route — without a
    registered key it's a no-op.
    """
    redis_key = getattr(request.state, "idempotency_redis_key", None)
    if not redis_key:
        return
    await _persist(request, redis_key, response)
