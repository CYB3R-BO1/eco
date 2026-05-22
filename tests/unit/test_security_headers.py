"""Phase 6 WP5 — secure response headers + body-size cap.

These are unit-level smoke tests: drive the in-process app (no lifespan)
and assert the middleware stack actually emits the headers and rejects
oversized bodies before the route handler sees them.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from apps.api.main import create_app
from core.config.settings import (
    JWTKey,
    SecuritySettings,
    Settings,
    get_settings,
)


def _build_app(*, max_body_bytes: int | None = None) -> Settings:
    get_settings.cache_clear()
    settings = Settings()
    settings.security = SecuritySettings(
        jwt_keys=[JWTKey(kid="t", secret=SecretStr("test-secret"))],
        bootstrap_admin_secret=SecretStr("bootstrap"),
        max_body_bytes=max_body_bytes if max_body_bytes is not None else 1_048_576,
    )
    return settings


@pytest.mark.asyncio
async def test_secure_headers_present_on_health() -> None:
    settings = _build_app()
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in resp.headers["Content-Security-Policy"]
    # HSTS is prod-only — dev/test should NOT see it
    assert "Strict-Transport-Security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_only_in_production() -> None:
    settings = _build_app()
    settings.environment = "production"
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert "Strict-Transport-Security" in resp.headers
    assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]


@pytest.mark.asyncio
async def test_max_body_middleware_rejects_oversized_content_length() -> None:
    settings = _build_app(max_body_bytes=128)
    app = create_app(settings)
    big = "x" * 1024
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/iocs/extract",
            json={"text": big},
            headers={"Content-Length": str(len(big) + 32)},
        )
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"]["code"] == 413


@pytest.mark.asyncio
async def test_max_body_middleware_lets_small_body_through() -> None:
    settings = _build_app(max_body_bytes=1_048_576)
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Body is allowed past MaxBodyMiddleware; route requires auth so 401
        resp = await c.post("/api/v1/iocs/extract", json={"text": "hello"})
    assert resp.status_code == 401
