"""End-to-end: POST /firewall/decision → COMPLETED investigation +
graph subgraph + immutable audit row.

Skipped unless ``INTEGRATION=1`` — requires the docker compose stack.
"""
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
async def test_benign_prompt_allow_path() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/v1/firewall/decision",
            json={
                "prompt": "Summarize this article in three bullet points.",
                "target_model": {"provider": "openai", "model": "gpt-4"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "ALLOW"
        assert body["risk_level"] in {"SAFE", "SUSPICIOUS"}
        investigation_id = body["investigation_id"]

        # Investigation reached COMPLETED via CORRELATING.
        inv = await c.get(f"/api/v1/investigations/{investigation_id}")
        assert inv.status_code == 200
        assert inv.json()["status"] == "COMPLETED"

        # Graph subgraph contains Prompt, Agent, edges.
        sg = await c.get(f"/api/v1/graph/investigation/{investigation_id}")
        assert sg.status_code == 200
        payload = sg.json()
        labels = {label for node in payload["nodes"] for label in node["labels"]}
        assert "Prompt" in labels
        assert "Agent" in labels
        edge_types = {e["type"] for e in payload["edges"]}
        assert "PART_OF" in edge_types
        assert "ANALYZED_BY" in edge_types


@pytest.mark.asyncio
async def test_analyze_endpoint_is_read_only() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/v1/firewall/analyze",
            json={
                "prompt": "Summarize this article.",
                "target_model": {"provider": "openai", "model": "gpt-4"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert "investigation_id" not in body
        assert body["prompt_fingerprint"]
        assert "explainability" in body


@pytest.mark.asyncio
async def test_decision_response_omits_raw_prompt_field() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/v1/firewall/decision",
            json={
                "prompt": "Hello world",
                "target_model": {"provider": "openai", "model": "gpt-4"},
            },
        )
        body = r.json()
        # The response shape should NEVER include the raw input.
        forbidden = {"prompt", "raw_prompt", "prompt_text"}
        assert not (forbidden & body.keys()), forbidden & body.keys()
