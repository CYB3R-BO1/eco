"""Health, liveness, and readiness endpoints.

* ``GET /health`` — cheap static OK; safe for load-balancer probes.
* ``GET /live``   — Kubernetes liveness probe; proves the process is up.
* ``GET /ready``  — Kubernetes readiness probe; verifies every downstream.
  Healthchecks run in parallel; if any component is down the response is 503.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from apps.api.dependencies import DatabaseDep, Neo4jDep, RedisDep
from schemas.api.health import ComponentStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready")
async def ready(db: DatabaseDep, redis: RedisDep, neo4j: Neo4jDep) -> JSONResponse:
    pg_ok, redis_ok, neo4j_ok = await asyncio.gather(
        db.healthcheck(),
        redis.healthcheck(),
        neo4j.healthcheck(),
    )

    components = [
        ComponentStatus(name="postgres", healthy=pg_ok),
        ComponentStatus(name="redis", healthy=redis_ok),
        ComponentStatus(name="neo4j", healthy=neo4j_ok),
    ]
    all_ok = all(c.healthy for c in components)
    payload = ReadinessResponse(
        status="ready" if all_ok else "not_ready",
        components=components,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload.model_dump(),
    )
