"""Request-level authentication dependency (Phase 6 WP3).

``get_current_principal`` parses the ``Authorization: Bearer ...`` header,
verifies the JWT via :mod:`core.security.jwt`, and returns an immutable
:class:`Principal`. On failure it raises :class:`HTTPException(401)` so the
existing exception handler emits the standard error envelope, increments
``auth_denials_total{reason=...}``, and logs ``auth.denied`` with the
structured reason (token contents are NEVER logged — only ``kid``,
``subject``, and ``role`` once verified).

Health endpoints (``/health``, ``/live``, ``/ready``) and the separate
metrics server stay outside this dependency, per WP3 requirement.
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config.settings import Settings, get_settings
from core.logging.context import bind_subject
from core.observability.metrics import AUTH_DENIALS_TOTAL
from core.security.jwt import DecodedToken, JWTError, decode_token
from core.security.principal import Principal

log = structlog.get_logger(__name__)

# ``auto_error=False`` so we control the 401 envelope (the default FastAPI
# error doesn't go through our handler chain).
_bearer_scheme = HTTPBearer(auto_error=False, bearer_format="JWT")


def _record_denial(reason: str, *, kid: str | None = None) -> None:
    AUTH_DENIALS_TOTAL.labels(reason=reason).inc()
    log.warning("auth.denied", reason=reason, kid=kid)


def _settings_from_request(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = get_settings()
    return settings  # type: ignore[no-any-return]


async def get_current_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        _record_denial("missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = _settings_from_request(request)
    try:
        decoded: DecodedToken = decode_token(
            credentials.credentials, security=settings.security
        )
    except JWTError as exc:
        _record_denial(exc.reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    bind_subject(decoded.subject)
    log.debug("auth.ok", subject=decoded.subject, role=decoded.role, kid=decoded.kid)
    return Principal(
        subject=decoded.subject,
        role=decoded.role,
        scopes=decoded.scopes,
        token_kid=decoded.kid,
    )


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]
