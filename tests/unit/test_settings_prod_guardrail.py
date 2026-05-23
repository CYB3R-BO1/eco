"""Phase 7 WP1 — production-environment startup guardrail.

Two failure modes the guardrail must catch on boot:

1. ``SECURITY_JWT_KEYS`` left unset in prod → tokens signed with the
   dev-default sentinel string.
2. ``SECURITY_BOOTSTRAP_ADMIN_SECRET`` empty in prod → admin surface
   silently locked; better to surface the misconfiguration at startup.

Dev / test environments keep the friendly defaults so local workflows
aren't disrupted.
"""
from __future__ import annotations

import pytest
from pydantic import SecretStr

from core.config.settings import JWTKey, SecuritySettings, Settings


def _safe_security() -> SecuritySettings:
    return SecuritySettings(
        jwt_keys=[JWTKey(kid="prod", secret=SecretStr("a-real-long-random-secret"))],
        bootstrap_admin_secret=SecretStr("operator-bootstrap-secret"),
    )


def test_development_keeps_dev_defaults() -> None:
    s = Settings(environment="development")
    # Default jwt_keys carries the dev sentinel; this must NOT raise.
    assert s.security.jwt_keys[0].secret.get_secret_value() == "change-me-dev-only"


def test_testing_keeps_dev_defaults() -> None:
    Settings(environment="testing")  # no raise


def test_production_with_safe_secrets_passes() -> None:
    Settings(environment="production", security=_safe_security())  # no raise


def test_production_with_dev_jwt_secret_fails() -> None:
    with pytest.raises(ValueError, match="dev-default JWT signing key"):
        Settings(environment="production")  # uses dev defaults


def test_production_with_empty_bootstrap_secret_fails() -> None:
    with pytest.raises(ValueError, match="SECURITY_BOOTSTRAP_ADMIN_SECRET"):
        Settings(
            environment="production",
            security=SecuritySettings(
                jwt_keys=[JWTKey(kid="prod", secret=SecretStr("a-real-secret"))],
                bootstrap_admin_secret=SecretStr(""),
            ),
        )


def test_production_with_empty_jwt_keys_list_fails() -> None:
    with pytest.raises(ValueError, match="dev-default JWT signing key"):
        Settings(
            environment="production",
            security=SecuritySettings(
                jwt_keys=[],
                bootstrap_admin_secret=SecretStr("ok"),
            ),
        )
