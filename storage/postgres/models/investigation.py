"""Investigation ORM model.

PLAN.md §5 `investigations` table. ``status`` is the only column that
``LifecycleManager.transition`` ever updates — all other mutations are
controlled by domain services. ``schema_version`` lets us replay old
investigations against their original schema (PLAN.md §11.5).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, TimestampMixin, UUIDMixin
from investigation.lifecycle.states import InvestigationState

if TYPE_CHECKING:
    pass


class Investigation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "investigations"

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[InvestigationState] = mapped_column(
        SQLEnum(InvestigationState, name="investigation_status_enum", native_enum=True),
        nullable=False,
        default=InvestigationState.CREATED,
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
