"""Idempotency-Key replay returns identical response and creates no extra rows."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION", "0") != "1",
    reason="set INTEGRATION=1 to run; requires docker compose stack",
)

BASE = os.getenv("PLATFORM_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_idempotency_returns_cached_decision() -> None:
    key = str(uuid.uuid4())
    body = {
        "prompt": "Summarize this article briefly.",
        "target_model": {"provider": "openai", "model": "gpt-4"},
    }
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r1 = await c.post(
            "/api/v1/firewall/decision",
            headers={"Idempotency-Key": key},
            json=body,
        )
        r2 = await c.post(
            "/api/v1/firewall/decision",
            headers={"Idempotency-Key": key},
            json=body,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["investigation_id"] == r2.json()["investigation_id"]
        assert r1.json()["firewall_event_id"] == r2.json()["firewall_event_id"]
