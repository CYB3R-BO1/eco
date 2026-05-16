"""Centralized exception handlers.

All handlers emit a uniform error envelope::

    {"error": {"code": <int>, "message": <str>, "details"?: <list|dict>}}

4xx logs at ``warning``; the catch-all 500 logs at ``exception`` with stack
info. The catch-all exists so unhandled errors never leak stack traces to
clients — they live only in logs.

Phase 2 also maps the domain exceptions raised by the IOC pipeline
(``InvalidTransitionError``, ``IngestValidationError``,
``EvidenceValidationError``) onto the same envelope.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from evidence.validation import EvidenceValidationError
from investigation.extraction.extractor import TooLargeError, TooManyIocsError
from investigation.ingestion.validation import IngestValidationError
from investigation.lifecycle.manager import InvalidTransitionError

log = structlog.get_logger("exception")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        log.warning(
            "http_exception",
            status=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        log.warning("validation_error", errors=exc.errors(), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": 422,
                    "message": "validation_error",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(IngestValidationError)
    async def ingest_validation_handler(
        request: Request, exc: IngestValidationError
    ) -> JSONResponse:
        log.warning("ingest_validation_error", message=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": 400, "message": str(exc)}},
        )

    @app.exception_handler(EvidenceValidationError)
    async def evidence_validation_handler(
        request: Request, exc: EvidenceValidationError
    ) -> JSONResponse:
        log.warning("evidence_validation_error", message=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": 422, "message": str(exc)}},
        )

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition_handler(
        request: Request, exc: InvalidTransitionError
    ) -> JSONResponse:
        log.warning(
            "invalid_transition",
            current=exc.current.value,
            target=exc.target.value,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": 409, "message": str(exc)}},
        )

    @app.exception_handler(TooLargeError)
    async def too_large_handler(request: Request, exc: TooLargeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"error": {"code": 413, "message": str(exc)}},
        )

    @app.exception_handler(TooManyIocsError)
    async def too_many_handler(request: Request, exc: TooManyIocsError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": 422, "message": str(exc)}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": 500, "message": "internal_server_error"}},
        )
