"""End-to-end integration test for the IOC pipeline.

Skipped unless the data tier is up (docker compose up). Use
``pytest tests/integration -v`` after ``make migrate``.
"""
from __future__ import annotations

import asyncio
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
async def test_extract_stateless() -> None:
    async with httpx.AsyncClient(base_url=BASE) as c:
        r = await c.post(
            "/api/v1/iocs/extract",
            json={"text": "Suspicious hxxp://Malicious[.]com from 8.8.8.8"},
        )
    assert r.status_code == 200
    payload = r.json()
    types = {e["entity_type"] for e in payload["extracted"]}
    assert "url" in types
    assert "ip" in types


@pytest.mark.asyncio
async def test_ingest_full_pipeline() -> None:
    idem_key = str(uuid.uuid4())
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/v1/iocs/ingest",
            headers={"Idempotency-Key": idem_key},
            json={"artifact": "https://Google.com/login", "type": "url"},
        )
        assert r.status_code == 202
        investigation_id = r.json()["investigation_id"]

        # Idempotent replay returns same body.
        r2 = await c.post(
            "/api/v1/iocs/ingest",
            headers={"Idempotency-Key": idem_key},
            json={"artifact": "https://Google.com/login", "type": "url"},
        )
        assert r2.json() == r.json()

        # Poll until COMPLETED (or FAILED).
        terminal = {"COMPLETED", "FAILED"}
        for _ in range(20):
            await asyncio.sleep(0.5)
            inv = await c.get(f"/api/v1/investigations/{investigation_id}")
            assert inv.status_code == 200
            body = inv.json()
            if body["status"] in terminal:
                break
        assert body["status"] == "COMPLETED"
        assert body["evidence_refs"], "should have at least the head evidence"
        event_types = [e["event_type"] for e in body["timeline"]]
        assert "INVESTIGATION_CREATED" in event_types
        assert "IOC_INGESTED" in event_types
        assert "INVESTIGATION_STATE_CHANGED" in event_types
