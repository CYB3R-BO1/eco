"""Investigation lifecycle manager.

Only this class can UPDATE ``investigations.status``. Every transition is
validated against ``ALLOWED_TRANSITIONS`` and emits
``INVESTIGATION_STATE_CHANGED`` in the same transaction — so the audit log
can never disagree with the actual state column.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.events.emitter import EventEmitter
from core.events.types import EventType
from investigation.lifecycle.states import (
    ALLOWED_TRANSITIONS,
    InvestigationState,
    is_valid_transition,
)
from storage.postgres.models.investigation import Investigation

log = structlog.get_logger(__name__)


class InvalidTransitionError(ValueError):
    """Raised when a (current → target) transition is not in the allowlist."""

    def __init__(self, current: InvestigationState, target: InvestigationState) -> None:
        super().__init__(f"invalid transition: {current.value} → {target.value}")
        self.current = current
        self.target = target


class LifecycleManager:
    def __init__(self, event_emitter: EventEmitter) -> None:
        self._emitter = event_emitter

    async def transition(
        self,
        session: AsyncSession,
        investigation_id: uuid.UUID,
        target_state: InvestigationState,
        *,
        reason: str,
    ) -> None:
        # SELECT ... FOR UPDATE prevents concurrent transitions from racing.
        stmt = (
            select(Investigation)
            .where(Investigation.id == investigation_id)
            .with_for_update()
        )
        investigation = (await session.execute(stmt)).scalar_one()
        current = investigation.status

        if current == target_state:
            return  # idempotent no-op

        if not is_valid_transition(current, target_state):
            log.warning(
                "lifecycle.invalid_transition",
                investigation_id=str(investigation_id),
                current=current.value,
                target=target_state.value,
                allowed=[s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset())],
            )
            raise InvalidTransitionError(current, target_state)

        investigation.status = target_state
        await self._emitter.emit(
            session,
            EventType.INVESTIGATION_STATE_CHANGED,
            source="lifecycle",
            investigation_id=investigation_id,
            target=target_state.value,
            metadata={
                "from": current.value,
                "to": target_state.value,
                "reason": reason,
            },
        )
        log.info(
            "lifecycle.transitioned",
            investigation_id=str(investigation_id),
            from_state=current.value,
            to_state=target_state.value,
        )
