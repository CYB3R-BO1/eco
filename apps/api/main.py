"""FastAPI application factory.

``create_app`` builds and returns the app; the module-level ``app`` is what
uvicorn loads. The factory pattern lets tests construct isolated instances —
important because ``get_settings()`` is ``lru_cache``d, so individual tests
can pass in custom :class:`Settings` to override defaults.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.exceptions import register_exception_handlers
from apps.api.lifespan import lifespan
from apps.api.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from apps.api.middleware_body_limit import MaxBodyMiddleware
from apps.api.middleware_metrics import RequestMetricsMiddleware
from apps.api.middleware_ratelimit import build_limiter
from apps.api.middleware_security import SecureHeadersMiddleware
from apps.api.routers.health import router as health_router
from apps.api.routers.v1 import router as v1_router
from core.config.settings import Settings, get_settings
from core.logging.setup import configure_logging
from core.observability.instrumentation import instrument_fastapi
from core.observability.tracing import init_tracing


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.logging.level, json_output=settings.logging.json)
    init_tracing(
        service_name=settings.observability.service_name,
        otlp_endpoint=settings.observability.otlp_endpoint
        if settings.observability.otel_enabled
        else None,
        otel_insecure=settings.observability.otel_insecure,
        service_version=settings.observability.service_version,
    )

    log = structlog.get_logger(__name__)
    log.info("app.create", environment=settings.environment, debug=settings.debug)

    is_prod = settings.environment == "production"
    app = FastAPI(
        title="AI-Native Cybersecurity & AI Safety Platform",
        description="Phase 1 — Foundation. AI-for-Security + Security-for-AI MVP.",
        version="0.1.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Starlette runs middleware added later first (outermost). Phase 6 WP5
    # final order, outermost → innermost: CorrelationId, SecureHeaders,
    # MaxBody, RequestMetrics, RequestLogging, then CORS. CORS is added
    # FIRST (innermost) so it sees the final response; CorrelationId is
    # added LAST (outermost) so contextvars are bound before any downstream
    # middleware logs anything.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestMetricsMiddleware)
    app.add_middleware(MaxBodyMiddleware, max_bytes=settings.security.max_body_bytes)
    app.add_middleware(
        SecureHeadersMiddleware,
        is_production=settings.environment == "production",
    )
    app.add_middleware(CorrelationIdMiddleware)

    # Rate limiter — optional, depends on slowapi being installed.
    limiter = build_limiter(settings)
    if limiter is not None:
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware

        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)

        @app.exception_handler(RateLimitExceeded)
        async def _rate_limit_handler(request, exc):  # type: ignore[no-untyped-def]
            from fastapi.responses import JSONResponse

            log.warning(
                "rate_limit.exceeded",
                path=request.url.path,
                detail=str(exc),
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": 429,
                        "message": "rate limit exceeded",
                    }
                },
                headers={"Retry-After": "60"},
            )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    # OpenTelemetry FastAPI instrumentation must run AFTER routes are mounted
    # so it can resolve route templates from the operation name. Safe to call
    # even when the OTLP exporter is disabled — spans just go nowhere.
    if settings.observability.otel_enabled:
        instrument_fastapi(app)

    return app


app = create_app()
