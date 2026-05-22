"""Phase 6 WP3 — JWT encode/decode + structured denial reasons.

Every test here asserts behaviour that the production code path depends on:
the closed set of denial reasons is what ``auth_denials_total`` labels are
keyed by, so adding a new path here means updating the metric contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from pydantic import SecretStr

from core.config.settings import JWTKey, SecuritySettings
from core.security.jwt import JWTError, decode_token, encode_token


def _security(*keys: JWTKey) -> SecuritySettings:
    return SecuritySettings(
        jwt_keys=list(keys) or [JWTKey(kid="active", secret=SecretStr("primary-secret"))],
        jwt_issuer="ai-security-platform",
        jwt_audience="ai-security-platform",
        bootstrap_admin_secret=SecretStr("admin-only"),
    )


def test_roundtrip_active_key() -> None:
    sec = _security()
    token = encode_token(subject="alice", role="analyst", scopes=["read"], security=sec)
    decoded = decode_token(token, security=sec)
    assert decoded.subject == "alice"
    assert decoded.role == "analyst"
    assert decoded.scopes == frozenset({"read"})
    assert decoded.kid == "active"


def test_expired_token_yields_expired_reason() -> None:
    sec = _security()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = encode_token(
        subject="alice", role="analyst", ttl_seconds=60, security=sec, now=past
    )
    with pytest.raises(JWTError) as exc:
        decode_token(token, security=sec)
    assert exc.value.reason == "expired"


def test_wrong_signature_yields_invalid_signature() -> None:
    sec = _security()
    token = encode_token(subject="alice", role="analyst", security=sec)
    other = _security(JWTKey(kid="active", secret=SecretStr("DIFFERENT-secret")))
    with pytest.raises(JWTError) as exc:
        decode_token(token, security=other)
    assert exc.value.reason == "invalid_signature"


def test_unknown_kid_after_rotation_drop() -> None:
    sec = _security(JWTKey(kid="old", secret=SecretStr("old-secret")))
    token = encode_token(subject="alice", role="analyst", security=sec)
    # Operator dropped the old kid entirely (would normally keep both).
    rotated = _security(JWTKey(kid="new", secret=SecretStr("new-secret")))
    with pytest.raises(JWTError) as exc:
        decode_token(token, security=rotated)
    assert exc.value.reason == "unknown_kid"


def test_wrong_audience() -> None:
    sec = _security()
    token = encode_token(subject="alice", role="analyst", security=sec)
    other = SecuritySettings(
        jwt_keys=sec.jwt_keys,
        jwt_issuer=sec.jwt_issuer,
        jwt_audience="some-other-audience",
    )
    with pytest.raises(JWTError) as exc:
        decode_token(token, security=other)
    assert exc.value.reason == "wrong_audience"


def test_wrong_issuer() -> None:
    sec = _security()
    token = encode_token(subject="alice", role="analyst", security=sec)
    other = SecuritySettings(
        jwt_keys=sec.jwt_keys,
        jwt_issuer="some-other-issuer",
        jwt_audience=sec.jwt_audience,
    )
    with pytest.raises(JWTError) as exc:
        decode_token(token, security=other)
    assert exc.value.reason == "wrong_issuer"


def test_missing_token_string() -> None:
    sec = _security()
    with pytest.raises(JWTError) as exc:
        decode_token("", security=sec)
    assert exc.value.reason == "missing"


def test_malformed_token() -> None:
    sec = _security()
    with pytest.raises(JWTError) as exc:
        decode_token("not.a.jwt", security=sec)
    assert exc.value.reason == "malformed"


def test_token_signed_without_kid_header_rejected() -> None:
    sec = _security()
    bad = pyjwt.encode(
        {
            "sub": "alice",
            "role": "analyst",
            "iss": sec.jwt_issuer,
            "aud": sec.jwt_audience,
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int(datetime.now(timezone.utc).timestamp() + 60),
        },
        sec.jwt_keys[0].secret.get_secret_value(),
        algorithm=sec.jwt_algorithm,
    )
    with pytest.raises(JWTError) as exc:
        decode_token(bad, security=sec)
    assert exc.value.reason == "malformed"


def test_rotation_keeps_old_tokens_valid() -> None:
    sec = _security(JWTKey(kid="old", secret=SecretStr("old-secret")))
    token = encode_token(subject="alice", role="analyst", security=sec)

    rotated = SecuritySettings(
        jwt_keys=[
            JWTKey(kid="new", secret=SecretStr("new-secret")),
            JWTKey(kid="old", secret=SecretStr("old-secret")),
        ],
        jwt_issuer=sec.jwt_issuer,
        jwt_audience=sec.jwt_audience,
    )
    decoded = decode_token(token, security=rotated)
    assert decoded.kid == "old"
    assert decoded.subject == "alice"
