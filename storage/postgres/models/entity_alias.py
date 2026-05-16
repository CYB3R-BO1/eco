"""Entity Resolution canonical-entity table.

PLAN.md §3 ``entity_aliases``. Every observed value of an IOC type resolves
to exactly one ``entity_id`` keyed on the canonical form. Variants record
the original observed forms (case_variant, protocol_stripped, child_url, …).
Unique constraint enforces one canonical entity per (form, type).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, TimestampMixin, UUIDMixin
from resolution.types import EntityType


class EntityAlias(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entity_aliases"

    entity_type: Mapped[EntityType] = mapped_column(
        SQLEnum(EntityType, name="entity_type_enum", native_enum=True),
        nullable=False,
    )
    canonical_form: Mapped[str] = mapped_column(String(2048), nullable=False)
    variants: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    __table_args__ = (
        UniqueConstraint("canonical_form", "entity_type", name="uq_entity_aliases_form_type"),
    )
