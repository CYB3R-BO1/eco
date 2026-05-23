"""SQLAlchemy slow-query logger (Phase 6 WP10).

Hooks into the ``before_cursor_execute`` / ``after_cursor_execute`` events
on the engine to time every statement and emit a structured log line when
the elapsed time exceeds ``observability.slow_query_threshold_ms``.

CLAUDE.md invariant #12 forbids logging bound parameter values — they
may contain raw prompt text, evidence content, or user input. We log the
SQL **template** verbatim and the SHA-256 of the bound parameters, so an
operator can correlate a slow plan against the query shape without ever
seeing the data.
"""
from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.engine import Engine

from core.security.hashing import sha256_hex

log = structlog.get_logger(__name__)


# Sentinel attribute set on an engine once a listener pair has been
# attached. SQLAlchemy ``event.listens_for`` registers globally and
# doesn't deduplicate, so a second call would double-log every query.
# Tests that build multiple engines hit this constantly without the
# guard.
_INSTALLED_ATTR = "_ai_security_slow_query_installed"


def install_slow_query_logger(engine: Engine, *, threshold_ms: int) -> None:
    """Wire the listener pair onto ``engine``. Idempotent.

    Phase 7 WP3: a sentinel attribute on the engine prevents
    double-attach. Calling this function repeatedly on the same engine
    is now a no-op — important for test fixtures that build engines per
    test and for lifespan retries during reconnect.
    """
    target = engine.sync_engine if hasattr(engine, "sync_engine") else engine
    if getattr(target, _INSTALLED_ATTR, False):
        log.debug("slow_query_logger.already_installed")
        return

    @event.listens_for(target, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        context._slow_query_start = time.perf_counter()  # type: ignore[attr-defined]

    @event.listens_for(target, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        start = getattr(context, "_slow_query_start", None)
        if start is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms < threshold_ms:
            return
        log.warning(
            "db.slow_query",
            statement_template=_normalize_statement(statement),
            params_fingerprint=_params_fingerprint(parameters),
            duration_ms=round(elapsed_ms, 2),
            executemany=bool(executemany),
            threshold_ms=threshold_ms,
        )

    setattr(target, _INSTALLED_ATTR, True)


def _normalize_statement(statement: str) -> str:
    """Collapse whitespace so the log shape is stable across formatting."""
    return " ".join(statement.split())


def _params_fingerprint(parameters: Any) -> str:
    """Stable SHA-256 of bound parameters — never the values themselves.

    Returns an empty string when parameters are absent so the log line
    stays grep-friendly.
    """
    if not parameters:
        return ""
    try:
        return sha256_hex(repr(parameters))
    except Exception:  # noqa: BLE001 — never let logging crash the request
        return "fingerprint_failed"
