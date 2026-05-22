"""Phase 6 WP3 — auth dependency wired into v1 routers.

These tests run against the in-process FastAPI app (no lifespan, so no
Postgres/Redis/Neo4j) and exercise the auth boundary via the only route
that does not need infrastructure: ``GET /api/v1/tokens/whoami``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from apps.api.main import create_app
from core.config.settings import (
    JWTKey,
    SecuritySettings,
    Settings,
    get_settings,
)
from core.observability.metrics import AUTH_DENIALS_TOTAL, PERMISSION_DENIALS_TOTAL
from core.security.jwt import encode_token


def _build_app() -> tuple[FastAPI, Settings]:
    # Fresh settings so the test doesn't share JWT keys with the module-level
    # app instance (which is constructed at import-time with defaults).
    get_settings.cache_clear()
    settings = Settings()
    settings.security = SecuritySettings(
        jwt_keys=[JWTKey(kid="t", secret=SecretStr("test-secret-for-unit-tests"))],
        jwt_issuer="ai-security-platform",
        jwt_audience="ai-security-platform",
        bootstrap_admin_secret=SecretStr("super-secret-bootstrap"),
    )
    app = create_app(settings)
    return app, settings


def _denial_value(reason: str) -> float:
    counter = AUTH_DENIALS_TOTAL.labels(reason=reason)
    return counter._value.get()  # type: ignore[attr-defined,no-any-return]


def _permission_denial_value(role: str, permission: str) -> float:
    counter = PERMISSION_DENIALS_TOTAL.labels(role=role, permission=permission)
    return counter._value.get()  # type: ignore[attr-defined,no-any-return]


@pytest.mark.asyncio
async def test_unauthenticated_v1_request_returns_401() -> None:
    app, _ = _build_app()
    before = _denial_value("missing")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/tokens/whoami")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate", "").lower().startswith("bearer")
    assert _denial_value("missing") == before + 1


@pytest.mark.asyncio
async def test_valid_token_reaches_route() -> None:
    app, settings = _build_app()
    token = encode_token(
        subject="alice",
        role="analyst",
        scopes=["investigation:read"],
        security=settings.security,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/tokens/whoami",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == "alice"
    assert body["role"] == "analyst"
    assert body["token_kid"] == "t"
    assert "investigation:read" in body["scopes"]


@pytest.mark.asyncio
async def test_expired_token_increments_denial_metric() -> None:
    app, settings = _build_app()
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    token = encode_token(
        subject="alice",
        role="analyst",
        ttl_seconds=60,
        security=settings.security,
        now=past,
    )
    before = _denial_value("expired")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/tokens/whoami",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 401
    assert _denial_value("expired") == before + 1


@pytest.mark.asyncio
async def test_health_endpoints_remain_open() -> None:
    app, _ = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for path in ("/health", "/live"):
            resp = await c.get(path)
            assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_readonly_role_denied_write_route() -> None:
    """Phase 6 WP4 — readonly token on a write route returns 403 and
    increments ``permission_denials_total{role,permission}``."""
    app, settings = _build_app()
    token = encode_token(
        subject="ro-user",
        role="readonly",
        security=settings.security,
    )
    before = _permission_denial_value("readonly", "ioc:ingest")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/iocs/ingest",
            json={"artifact": "1.2.3.4 phishing.example"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403
    assert resp.json() == {"error": {"code": 403, "message": "permission_denied"}}
    assert _permission_denial_value("readonly", "ioc:ingest") == before + 1


@pytest.mark.asyncio
async def test_analyst_role_passes_authorization_gate() -> None:
    """An analyst has IOC_INGEST. The route should NOT 403; any further
    failure (e.g. missing DB in the no-lifespan test app) is past the
    authorization gate, which is what we're asserting here."""
    app, settings = _build_app()
    token = encode_token(
        subject="alice",
        role="analyst",
        security=settings.security,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/iocs/ingest",
            json={"artifact": "1.2.3.4"},
            headers={"Authorization": f"Bearer {token}"},
        )
    # Not 401 (auth ok) and not 403 (authz ok). Likely 500 because no DB.
    assert resp.status_code not in (401, 403)


@pytest.mark.asyncio
async def test_issue_token_requires_bootstrap_secret() -> None:
    app, _ = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # No header → 403
        resp = await c.post(
            "/api/v1/tokens/issue",
            json={"subject": "ops", "role": "admin"},
        )
        assert resp.status_code == 403

        # Wrong secret → 403
        resp = await c.post(
            "/api/v1/tokens/issue",
            json={"subject": "ops", "role": "admin"},
            headers={"X-Admin-Bootstrap-Secret": "wrong"},
        )
        assert resp.status_code == 403

        # Correct secret → 201 + token returned
        resp = await c.post(
            "/api/v1/tokens/issue",
            json={"subject": "ops", "role": "admin"},
            headers={"X-Admin-Bootstrap-Secret": "super-secret-bootstrap"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["token"]
        assert body["kid"] == "t"
        assert body["subject"] == "ops"
        assert body["role"] == "admin"
