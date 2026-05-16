from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_live_endpoint(client: AsyncClient) -> None:
    response = await client.get("/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_correlation_id_round_trip(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Correlation-ID": "test-corr-id"})
    assert response.headers["X-Correlation-ID"] == "test-corr-id"


@pytest.mark.asyncio
async def test_correlation_id_generated_when_missing(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert "X-Correlation-ID" in response.headers
    assert response.headers["X-Correlation-ID"]
