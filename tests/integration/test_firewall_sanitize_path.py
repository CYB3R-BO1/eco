"""PII-laden prompts → SANITIZE with sanitized_prompt + redactions."""
from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION", "0") != "1",
    reason="set INTEGRATION=1 to run; requires docker compose stack",
)

BASE = os.getenv("PLATFORM_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_sanitize_path_masks_pii() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/v1/firewall/decision",
            json={
                "prompt": (
                    "Please look up my account; my email is alice@example.com "
                    "and my phone is +14155551234."
                ),
                "target_model": {"provider": "openai", "model": "gpt-4"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] in {"SANITIZE", "REQUIRE_REVIEW", "BLOCK"}
        if body["decision"] == "SANITIZE":
            assert body["sanitized_prompt"]
            assert "alice@example.com" not in body["sanitized_prompt"]
            assert "+14155551234" not in body["sanitized_prompt"]
            assert body["redactions"]
