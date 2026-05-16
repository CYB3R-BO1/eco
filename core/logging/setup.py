"""Structlog configuration.

The canonical structlog + stdlib bridge: structlog loggers and ``logging``
loggers both emit through a single ``StreamHandler`` formatted by
``ProcessorFormatter``. That means uvicorn/SQLAlchemy/Alembic log lines are
rendered with the same JSON shape as our own structlog output, with correlation
IDs from ``structlog.contextvars`` automatically attached.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    pre_chain: list[Any] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            *pre_chain,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # Route uvicorn's loggers through the same handler instead of its default ones.
    for noisy in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(noisy)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(log_level)
