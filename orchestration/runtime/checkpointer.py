"""LangGraph checkpointer wrapper.

Phase 5 uses ``langgraph-checkpoint-postgres`` for durability — a process
restart between nodes resumes from the last checkpoint. When the package
is not installed (e.g. minimal dev install) we fall back to
:class:`MemorySaver` so the import doesn't break; orchestration paths
that *require* durability will fail at runtime if the postgres saver was
expected.

We do not declare the ``langgraph_checkpoints`` table in our Alembic
migrations — the package owns its own schema and provides
``setup()``/``asetup()`` which we invoke once at startup (idempotent).
"""
from __future__ import annotations

import enum
import structlog

from core.config.settings import PostgresSettings

log = structlog.get_logger(__name__)


class CheckpointerKind(str, enum.Enum):
    POSTGRES = "POSTGRES"
    MEMORY = "MEMORY"


async def build_checkpointer(
    postgres: PostgresSettings,
    *,
    prefer: CheckpointerKind = CheckpointerKind.POSTGRES,
):
    """Return an async checkpointer instance.

    The returned object satisfies the LangGraph ``BaseCheckpointSaver``
    protocol. We import lazily so a missing optional package only breaks
    code paths that actually need the checkpointer.
    """
    if prefer is CheckpointerKind.POSTGRES:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import-not-found]
        except ImportError:
            log.warning(
                "checkpointer.postgres_unavailable_falling_back_to_memory",
                hint="install langgraph-checkpoint-postgres for durability",
            )
            return _memory_saver()
        # AsyncPostgresSaver.from_conn_string returns an async context manager.
        # The caller is responsible for entering/exiting it (lifespan does so).
        return AsyncPostgresSaver.from_conn_string(postgres.sync_dsn)
    return _memory_saver()


def _memory_saver():
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


async def setup_checkpointer(checkpointer) -> None:
    """Invoke ``setup`` if the checkpointer exposes one. Idempotent.

    ``MemorySaver`` does not require setup; ``AsyncPostgresSaver`` does
    (it creates ``langgraph_checkpoints`` + ``langgraph_checkpoint_writes``
    on first run).
    """
    setup = getattr(checkpointer, "setup", None) or getattr(checkpointer, "asetup", None)
    if setup is None:
        return
    result = setup()
    if hasattr(result, "__await__"):
        await result
    log.info("checkpointer.setup_complete", kind=type(checkpointer).__name__)
