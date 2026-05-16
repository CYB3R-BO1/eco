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
from apps.api.routers.health import router as health_router
from apps.api.routers.v1 import router as v1_router
from core.config.settings import Settings, get_settings
from core.logging.setup import configure_logging
from core.observability.tracing import init_tracing


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.logging.level, json_output=settings.logging.json)
    init_tracing(service_name="platform-api")

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

    # Starlette runs middleware added later first (outermost). We want the
    # correlation ID to be set before request logging emits its line, so add
    # the logger first (innermost) and the correlation middleware second.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
