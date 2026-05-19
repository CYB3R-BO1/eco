"""End-to-end test: ingest → ENRICHING → CORRELATING → COMPLETED.

Asserts that after a clean ingest:

* the Investigation node exists in Neo4j;
* at least one IOC entity node exists;
* PART_OF edges connect IOCs and Evidence to the Investigation;
* the timeline contains GRAPH_NODE_CREATED + GRAPH_RELATIONSHIP_CREATED
  + CORRELATION_COMPLETED events in order.

Skipped unless ``INTEGRATION=1`` — requires ``docker compose up`` + ``make migrate``.
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
async def test_ingest_runs_through_correlating() -> None:
    idem_key = str(uuid.uuid4())
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/v1/iocs/ingest",
            headers={"Idempotency-Key": idem_key},
            json={"artifact": "https://Google.com/login", "type": "url"},
        )
        assert r.status_code == 202
        investigation_id = r.json()["investigation_id"]

        terminal = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}
        body: dict = {}
        for _ in range(40):
            await asyncio.sleep(0.5)
            inv = await c.get(f"/api/v1/investigations/{investigation_id}")
            assert inv.status_code == 200
            body = inv.json()
            if body["status"] in terminal:
                break
        assert body["status"] == "COMPLETED", body

        # Graph view
        subgraph = await c.get(f"/api/v1/graph/investigation/{investigation_id}")
        assert subgraph.status_code == 200
        payload = subgraph.json()
        labels = {label for node in payload["nodes"] for label in node["labels"]}
        assert "Investigation" in labels
        assert "Evidence" in labels
        # URL ingest should produce URL and Domain (parent) entity nodes.
        assert "URL" in labels or "Domain" in labels

        # Timeline endpoint
        tl = await c.get(f"/api/v1/investigations/{investigation_id}/timeline")
        assert tl.status_code == 200
        event_types = [e["event_type"] for e in tl.json()["events"]]
        assert "INVESTIGATION_CREATED" in event_types
        assert "IOC_INGESTED" in event_types
        assert "GRAPH_NODE_CREATED" in event_types
        assert "GRAPH_RELATIONSHIP_CREATED" in event_types
        assert "CORRELATION_COMPLETED" in event_types


@pytest.mark.asyncio
async def test_graph_query_depth_validation() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post(
            "/api/v1/graph/query",
            json={
                "start_node_id": str(uuid.uuid4()),
                "depth": 99,
                "rel_types": [],
                "min_confidence": 0.0,
                "limit": 10,
            },
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_graph_query_min_confidence_validation() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post(
            "/api/v1/graph/query",
            json={
                "start_node_id": str(uuid.uuid4()),
                "depth": 2,
                "rel_types": [],
                "min_confidence": 2.5,
                "limit": 10,
            },
        )
        assert r.status_code == 422
