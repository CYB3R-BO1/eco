"""Token issuance + key rotation (Phase 6 WP3).

There is no user database — this is a closed-loop single-tenant MVP. The
``POST /tokens/issue`` endpoint is gated by ``bootstrap_admin_secret``
shared out-of-band with the operator; once issued, day-to-day RBAC
(WP4) is the real authorization surface.

Why not put this behind ``get_current_principal``: bootstrapping. An
operator with no token cannot mint themselves a token via that path.
The bootstrap secret breaks the chicken-and-egg.

``POST /tokens/rotate-key`` prepends a new ``kid`` to the in-process
keyset. Old tokens keep validating until they expire, which is the
non-disruptive rotation property HS256 + ``kid`` was chosen for. The
new keyset lives only in memory — persistent rotation is a deployment
concern (set ``SECURITY_JWT_KEYS`` env, restart).
"""
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr

from apps.api.auth import PrincipalDep
from core.config.settings import JWTKey, Settings, get_settings
from core.security.jwt import encode_token
from core.security.principal import Principal

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tokens", tags=["tokens"])


def _settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = get_settings()
    return settings  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(_settings)]


class IssueTokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=32)
    scopes: list[str] = Field(default_factory=list)
    ttl_seconds: int | None = Field(default=None, ge=60, le=86_400)


class IssueTokenResponse(BaseModel):
    token: str
    kid: str
    expires_at: datetime
    role: str
    subject: str


class RotateKeyRequest(BaseModel):
    new_kid: str = Field(min_length=1, max_length=64)
    new_secret: SecretStr


class RotateKeyResponse(BaseModel):
    active_kid: str
    known_kids: list[str]


def _require_bootstrap_secret(
    presented: str | None, settings: Settings, *, action: str
) -> None:
    """Constant-time check of the deploy-time bootstrap secret.

    Empty configured secret means the admin surface is locked — no caller
    can authenticate, so the endpoint always 403s. This is the safe default
    when ``SECURITY_BOOTSTRAP_ADMIN_SECRET`` was never set.
    """
    expected = settings.security.bootstrap_admin_secret.get_secret_value()
    if not expected:
        log.warning("admin.bootstrap_secret_unset", action=action)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin bootstrap secret not configured",
        )
    if not presented or not hmac.compare_digest(presented, expected):
        log.warning("admin.bootstrap_secret_invalid", action=action)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid admin bootstrap secret",
        )


@router.post(
    "/issue",
    response_model=IssueTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a JWT (bootstrap-admin gated)",
    description=(
        "Mints a signed HS256 JWT. Gated by the X-Admin-Bootstrap-Secret "
        "header — set the matching value via SECURITY_BOOTSTRAP_ADMIN_SECRET "
        "at deploy time."
    ),
)
async def issue_token(
    body: IssueTokenRequest,
    settings: SettingsDep,
    bootstrap_secret: Annotated[str | None, Header(alias="X-Admin-Bootstrap-Secret")] = None,
) -> IssueTokenResponse:
    _require_bootstrap_secret(bootstrap_secret, settings, action="issue")

    issued_at = datetime.now(timezone.utc)
    ttl = body.ttl_seconds or settings.security.jwt_default_ttl_seconds
    token = encode_token(
        subject=body.subject,
        role=body.role,
        scopes=body.scopes,
        ttl_seconds=ttl,
        security=settings.security,
        now=issued_at,
    )
    expires_at = datetime.fromtimestamp(issued_at.timestamp() + ttl, tz=timezone.utc)
    active_kid = settings.security.jwt_keys[0].kid
    log.info(
        "token.issued",
        subject=body.subject,
        role=body.role,
        kid=active_kid,
        ttl_seconds=ttl,
    )
    return IssueTokenResponse(
        token=token,
        kid=active_kid,
        expires_at=expires_at,
        role=body.role,
        subject=body.subject,
    )


@router.post(
    "/rotate-key",
    response_model=RotateKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate the active JWT signing key",
    description=(
        "Prepends a new (kid, secret) pair to the in-process keyset. Existing "
        "tokens continue validating against their original kid until they "
        "expire. Persist by updating SECURITY_JWT_KEYS in the environment."
    ),
)
async def rotate_key(
    body: RotateKeyRequest,
    settings: SettingsDep,
    bootstrap_secret: Annotated[str | None, Header(alias="X-Admin-Bootstrap-Secret")] = None,
) -> RotateKeyResponse:
    _require_bootstrap_secret(bootstrap_secret, settings, action="rotate")

    existing_kids = {k.kid for k in settings.security.jwt_keys}
    if body.new_kid in existing_kids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"kid {body.new_kid!r} already present in keyset",
        )

    new_entry = JWTKey(kid=body.new_kid, secret=body.new_secret)
    # Prepend so the new key is active; old keys stay for validation-only.
    settings.security.jwt_keys = [new_entry, *settings.security.jwt_keys]
    log.warning(
        "token.key_rotated",
        new_kid=body.new_kid,
        previous_active=next(iter(existing_kids), None),
    )
    return RotateKeyResponse(
        active_kid=body.new_kid,
        known_kids=[k.kid for k in settings.security.jwt_keys],
    )


@router.get(
    "/whoami",
    summary="Return the caller's resolved principal",
    description=(
        "Convenience introspection endpoint. Useful for clients verifying "
        "their token without making a real call. Returns nothing sensitive — "
        "only the subject, role, scopes, and the kid the token was signed by."
    ),
)
async def whoami(principal: PrincipalDep) -> dict[str, object]:
    return {
        "subject": principal.subject,
        "role": principal.role,
        "scopes": sorted(principal.scopes),
        "token_kid": principal.token_kid,
    }
