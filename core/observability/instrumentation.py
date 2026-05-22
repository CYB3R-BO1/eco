"""OpenTelemetry auto-instrumentation toggles.

All instrumentation calls live here so a single ``instrument_all`` invocation
during lifespan startup wires every supported library at once. Each call is
guarded so a missing optional package logs a warning rather than crashing
the app — useful for thin test environments that don't install every
instrumentor.

Per CLAUDE.md invariant #12 these instrumentors MUST NOT capture request
bodies or query parameter values. The default OTel SDK behavior is to record
operation names + targets but not payload content; we explicitly DO NOT
enable any ``capture_*_content`` flags.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

log = structlog.get_logger(__name__)


def instrument_fastapi(app: "FastAPI") -> None:
    """Auto-instrument FastAPI route handlers."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        log.warning("instrumentation.fastapi.skipped reason=package_missing")
        return
    FastAPIInstrumentor.instrument_app(app)
    log.info("instrumentation.fastapi.enabled")


def instrument_sqlalchemy(engine: Any) -> None:
    """Auto-instrument SQLAlchemy queries on the given (sync or async) engine."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except ImportError:
        log.warning("instrumentation.sqlalchemy.skipped reason=package_missing")
        return
    # async_engine.sync_engine is what the instrumentor wants.
    target = getattr(engine, "sync_engine", engine)
    SQLAlchemyInstrumentor().instrument(engine=target)
    log.info("instrumentation.sqlalchemy.enabled")


def instrument_redis() -> None:
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
    except ImportError:
        log.warning("instrumentation.redis.skipped reason=package_missing")
        return
    RedisInstrumentor().instrument()
    log.info("instrumentation.redis.enabled")


def instrument_httpx() -> None:
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        log.warning("instrumentation.httpx.skipped reason=package_missing")
        return
    HTTPXClientInstrumentor().instrument()
    log.info("instrumentation.httpx.enabled")


def instrument_neo4j() -> None:
    """Optional — official OTel package for Neo4j is community-maintained."""
    try:
        from opentelemetry.instrumentation.neo4j import Neo4jInstrumentor
    except ImportError:
        log.info("instrumentation.neo4j.skipped reason=package_missing")
        return
    Neo4jInstrumentor().instrument()
    log.info("instrumentation.neo4j.enabled")
