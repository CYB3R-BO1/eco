"""HS256 self-issued JWTs (Phase 6 WP3).

This is the closed-loop authentication primitive for the MVP — no
external IdP, no JWKS endpoint. The active signing key is the first
entry in ``SecuritySettings.jwt_keys``; older entries remain present to
keep in-flight tokens valid across a rotation. Every encoded token
carries a ``kid`` header so the decoder can look up the matching secret
without trying every key.

Why HS256 and not RS256: single-tenant single-process deployment, no
need to distribute public keys. RS256 is an additive migration — the
``kid`` indirection means call sites don't change.

CLAUDE.md invariant #12: token contents (``sub``, ``role``, ``kid``)
are safe to log; the token string itself is never logged.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import jwt as pyjwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from core.config.settings import JWTKey, SecuritySettings


class JWTError(Exception):
    """Base for any token-verification failure.

    ``reason`` is a short, label-safe string used by the metric counter
    ``auth_denials_total{reason=...}``. Keep it bounded — see
    ``_AUTH_DENIAL_REASONS`` for the closed set.
    """

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = reason


# Closed set of structured denial reasons. Keep the metric label cardinality
# bounded (invariant #12).
_AUTH_DENIAL_REASONS = frozenset(
    {
        "missing",
        "malformed",
        "invalid_signature",
        "expired",
        "wrong_issuer",
        "wrong_audience",
        "unknown_kid",
        "missing_claim",
    }
)


def _validate_reason(reason: str) -> str:
    if reason not in _AUTH_DENIAL_REASONS:
        raise ValueError(f"unknown auth denial reason: {reason}")
    return reason


@dataclass(frozen=True)
class DecodedToken:
    """The verified token payload, narrowed to the fields routes care about."""

    subject: str
    role: str
    scopes: frozenset[str]
    kid: str
    issued_at: datetime
    expires_at: datetime


def _key_lookup(security: SecuritySettings, kid: str) -> JWTKey:
    for entry in security.jwt_keys:
        if entry.kid == kid:
            return entry
    raise JWTError(_validate_reason("unknown_kid"), f"unknown kid: {kid!r}")


def _active_key(security: SecuritySettings) -> JWTKey:
    if not security.jwt_keys:
        raise JWTError("missing", "no signing keys configured")
    return security.jwt_keys[0]


def encode_token(
    *,
    subject: str,
    role: str,
    scopes: Iterable[str] = (),
    ttl_seconds: int | None = None,
    security: SecuritySettings,
    now: datetime | None = None,
) -> str:
    """Issue a new bearer token signed by the active ``kid``.

    Tests can pin ``now`` for deterministic expiry assertions; production
    callers leave it ``None`` so ``datetime.now(timezone.utc)`` is used.
    """
    active = _active_key(security)
    issued_at = now or datetime.now(timezone.utc)
    ttl = ttl_seconds if ttl_seconds is not None else security.jwt_default_ttl_seconds
    expires_at = issued_at.timestamp() + ttl

    payload: dict[str, Any] = {
        "iss": security.jwt_issuer,
        "aud": security.jwt_audience,
        "sub": subject,
        "role": role,
        "scopes": sorted(set(scopes)),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at),
    }
    return pyjwt.encode(
        payload,
        active.secret.get_secret_value(),
        algorithm=security.jwt_algorithm,
        headers={"kid": active.kid},
    )


def decode_token(token: str, *, security: SecuritySettings) -> DecodedToken:
    """Verify ``token`` and return its narrowed payload.

    Raises :class:`JWTError` with a structured ``reason`` on any failure.
    The caller (``apps.api.auth.get_current_principal``) is responsible for
    turning that into a 401 + the ``auth_denials_total`` counter increment.
    """
    if not token:
        raise JWTError(_validate_reason("missing"), "no token supplied")

    try:
        unverified_header = pyjwt.get_unverified_header(token)
    except DecodeError as e:
        raise JWTError(_validate_reason("malformed"), str(e)) from e

    kid = unverified_header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise JWTError(_validate_reason("malformed"), "kid header missing")

    key_entry = _key_lookup(security, kid)

    try:
        payload = pyjwt.decode(
            token,
            key_entry.secret.get_secret_value(),
            algorithms=[security.jwt_algorithm],
            audience=security.jwt_audience,
            issuer=security.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except ExpiredSignatureError as e:
        raise JWTError(_validate_reason("expired"), str(e)) from e
    except InvalidIssuerError as e:
        raise JWTError(_validate_reason("wrong_issuer"), str(e)) from e
    except InvalidAudienceError as e:
        raise JWTError(_validate_reason("wrong_audience"), str(e)) from e
    except InvalidSignatureError as e:
        raise JWTError(_validate_reason("invalid_signature"), str(e)) from e
    except MissingRequiredClaimError as e:
        raise JWTError(_validate_reason("missing_claim"), str(e)) from e
    except InvalidTokenError as e:
        raise JWTError(_validate_reason("malformed"), str(e)) from e

    subject = payload.get("sub")
    role = payload.get("role")
    if not isinstance(subject, str) or not subject:
        raise JWTError(_validate_reason("missing_claim"), "sub claim missing")
    if not isinstance(role, str) or not role:
        raise JWTError(_validate_reason("missing_claim"), "role claim missing")

    raw_scopes = payload.get("scopes") or []
    if not isinstance(raw_scopes, list) or not all(isinstance(s, str) for s in raw_scopes):
        raise JWTError(_validate_reason("malformed"), "scopes claim malformed")

    return DecodedToken(
        subject=subject,
        role=role,
        scopes=frozenset(raw_scopes),
        kid=kid,
        issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=timezone.utc),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
    )
