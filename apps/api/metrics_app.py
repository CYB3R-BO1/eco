"""Standalone ASGI app exposing Prometheus metrics.

Mounted on its own uvicorn server on ``OBSERVABILITY_METRICS_PORT`` (default
9090, bound to ``127.0.0.1``) so the public API on port 8000 never serves
``/metrics``. The Prometheus scrape stays unauthenticated by convention; the
public surface stays auth-gated.
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from core.observability.metrics import render_latest

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


async def _metrics_endpoint(_: Request) -> Response:
    return Response(content=render_latest(), media_type=CONTENT_TYPE_LATEST)


async def _liveness_endpoint(_: Request) -> Response:
    return PlainTextResponse("ok", status_code=200)


def create_metrics_app() -> Starlette:
    return Starlette(
        debug=False,
        routes=[
            Route("/metrics", _metrics_endpoint, methods=["GET"]),
            Route("/", _liveness_endpoint, methods=["GET"]),
        ],
    )
