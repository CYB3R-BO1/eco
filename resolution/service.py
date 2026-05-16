"""Entity Resolution gateway.

PLAN.md §3 + CLAUDE.md invariant #3. Every value that becomes a graph node or
an Evidence record passes through this service. Two entry points:

* :meth:`normalize` — pure, no DB. Used by the stateless extract endpoint.
* :meth:`resolve`   — persists the canonical entity (find-or-create) and the
                      input variant if it differs. Used by the ingest pipeline.

Both produce the same ``ResolvedEntity`` shape so downstream code doesn't
care which path was taken.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from resolution.alias_tracking import make_variant
from resolution.deduplication import append_variant, find_or_create_entity
from resolution.normalization import (
    normalize_domain,
    normalize_email,
    normalize_hash,
    normalize_ip,
    normalize_url,
    parent_domain,
)
from resolution.types import EntityType

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class NormalizedValue:
    canonical_form: str
    entity_type: EntityType
    original: str
    variant_relation: str | None  # None if input already equals canonical


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: uuid.UUID
    canonical_form: str
    entity_type: EntityType
    was_new: bool


class EntityResolutionService:
    def normalize(self, raw_value: str, entity_type: EntityType) -> NormalizedValue:
        """Pure normalization. No DB writes."""
        if entity_type is EntityType.DOMAIN:
            canonical = normalize_domain(raw_value)
        elif entity_type is EntityType.URL:
            canonical = normalize_url(raw_value)
        elif entity_type is EntityType.IP:
            canonical = normalize_ip(raw_value)
        elif entity_type is EntityType.EMAIL:
            canonical = normalize_email(raw_value)
        elif entity_type in (EntityType.HASH_MD5, EntityType.HASH_SHA1, EntityType.HASH_SHA256):
            canonical, derived_type = normalize_hash(raw_value)
            entity_type = derived_type
        else:
            canonical = raw_value.strip()

        relation = _classify_variant(raw_value, canonical, entity_type)
        return NormalizedValue(
            canonical_form=canonical,
            entity_type=entity_type,
            original=raw_value,
            variant_relation=relation,
        )

    async def resolve(
        self,
        session: AsyncSession,
        raw_value: str,
        entity_type: EntityType,
    ) -> ResolvedEntity:
        """Normalize, find-or-create the canonical entity, record variant."""
        normalized = self.normalize(raw_value, entity_type)

        initial_variants = (
            [make_variant(normalized.original, normalized.variant_relation)]
            if normalized.variant_relation
            else []
        )
        entity_id, was_new = await find_or_create_entity(
            session,
            canonical_form=normalized.canonical_form,
            entity_type=normalized.entity_type,
            initial_variants=initial_variants,
        )

        if not was_new and normalized.variant_relation:
            await append_variant(
                session,
                entity_id,
                make_variant(normalized.original, normalized.variant_relation),
            )

        # URLs additionally produce a child_url variant on the parent domain.
        if normalized.entity_type is EntityType.URL:
            try:
                parent = parent_domain(normalized.canonical_form)
            except ValueError:
                parent = None
            if parent:
                parent_id, parent_new = await find_or_create_entity(
                    session,
                    canonical_form=parent,
                    entity_type=EntityType.DOMAIN,
                    initial_variants=[make_variant(normalized.canonical_form, "child_url")],
                )
                if not parent_new:
                    await append_variant(
                        session,
                        parent_id,
                        make_variant(normalized.canonical_form, "child_url"),
                    )

        log.info(
            "entity.resolved",
            entity_id=str(entity_id),
            canonical_form=normalized.canonical_form,
            entity_type=normalized.entity_type.value,
            was_new=was_new,
        )
        return ResolvedEntity(
            entity_id=entity_id,
            canonical_form=normalized.canonical_form,
            entity_type=normalized.entity_type,
            was_new=was_new,
        )


def _classify_variant(original: str, canonical: str, entity_type: EntityType) -> str | None:
    if original == canonical:
        return None
    if original.lower() == canonical.lower():
        return "case_variant"
    if entity_type is EntityType.DOMAIN:
        # Protocol stripped from a URL-looking input.
        for scheme in ("https://", "http://", "ftp://"):
            if original.lower().startswith(scheme):
                return "protocol_stripped"
        if original.endswith("."):
            return "trailing_dot"
        return "other"
    return "other"
