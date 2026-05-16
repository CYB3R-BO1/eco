"""Upsert helper for ``entity_aliases``.

Uses Postgres `INSERT ... ON CONFLICT DO NOTHING RETURNING` plus a follow-up
SELECT. We can't use `RETURNING` alone on conflict-do-nothing because in the
conflict case no row is returned — so we fall through to SELECT to fetch the
existing row's id.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from resolution.alias_tracking import merge_variants
from resolution.types import EntityType
from storage.postgres.models.entity_alias import EntityAlias


async def find_or_create_entity(
    session: AsyncSession,
    *,
    canonical_form: str,
    entity_type: EntityType,
    initial_variants: list[dict] | None = None,
) -> tuple[uuid.UUID, bool]:
    """Return ``(entity_id, was_created)``."""
    new_id = uuid.uuid4()
    stmt = (
        pg_insert(EntityAlias)
        .values(
            id=new_id,
            entity_type=entity_type,
            canonical_form=canonical_form,
            variants=initial_variants or [],
        )
        .on_conflict_do_nothing(constraint="uq_entity_aliases_form_type")
        .returning(EntityAlias.id)
    )
    result = await session.execute(stmt)
    row_id = result.scalar_one_or_none()
    if row_id is not None:
        return row_id, True

    existing = await session.execute(
        select(EntityAlias).where(
            EntityAlias.canonical_form == canonical_form,
            EntityAlias.entity_type == entity_type,
        )
    )
    entity = existing.scalar_one()
    return entity.id, False


async def append_variant(
    session: AsyncSession, entity_id: uuid.UUID, variant: dict
) -> None:
    """Read-modify-write the variants list. Concurrent calls may race; for
    Phase 2's volume that's acceptable. Phase 5 can introduce a real merge
    operator on the JSONB column if it becomes a contention point."""
    entity = await session.get(EntityAlias, entity_id)
    if entity is None:
        return
    entity.variants = merge_variants(entity.variants, variant)
