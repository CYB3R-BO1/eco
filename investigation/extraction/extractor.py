"""IOC extraction from text or JSON.

Deterministic only — regex + per-type normalization. No AI. Hard limits
prevent runaway extraction (PLAN.md §3.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from investigation.extraction.patterns import PATTERNS, refang
from resolution.service import EntityResolutionService
from resolution.types import EntityType

log = structlog.get_logger(__name__)

MAX_INPUT_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IOCS_PER_PAYLOAD = 10_000


@dataclass(frozen=True)
class ExtractedIOC:
    value: str
    canonical_form: str
    entity_type: EntityType
    extraction_method: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


class TooLargeError(ValueError):
    pass


class TooManyIocsError(ValueError):
    pass


def extract_iocs(
    text: str,
    *,
    types: list[EntityType] | None = None,
    resolver: EntityResolutionService | None = None,
    source_context: str | None = None,
) -> list[ExtractedIOC]:
    """Extract, normalize, and deduplicate IOCs from ``text``.

    Does NOT touch the database — only the pure normalize() side of
    EntityResolutionService is used. Persisting canonical entities happens
    in the ingest pipeline, not here. The ``resolver`` arg is optional only
    so unit tests can supply a stub.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise TooLargeError("payload exceeds 10MB limit")

    resolver = resolver or EntityResolutionService()
    refanged = refang(text)
    was_defanged = refanged != text

    type_filter = set(types) if types else None
    seen: set[tuple[EntityType, str]] = set()
    out: list[ExtractedIOC] = []

    for entity_type, pattern in PATTERNS:
        if type_filter is not None and entity_type not in type_filter:
            # Hash patterns can promote; still allow if MD5/SHA1/SHA256 was asked for.
            continue
        for match in pattern.finditer(refanged):
            raw = match.group(0)
            try:
                normalized = resolver.normalize(raw, entity_type)
            except ValueError:
                continue

            dedup_key = (normalized.entity_type, normalized.canonical_form)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            confidence = 0.95 if not was_defanged else 0.85
            metadata: dict[str, Any] = {
                "match_start": match.start(),
                "match_end": match.end(),
                "defanged_input": was_defanged,
            }
            if source_context:
                metadata["source_context"] = source_context

            out.append(
                ExtractedIOC(
                    value=raw,
                    canonical_form=normalized.canonical_form,
                    entity_type=normalized.entity_type,
                    extraction_method="regex",
                    confidence=confidence,
                    metadata=metadata,
                )
            )

            if len(out) > MAX_IOCS_PER_PAYLOAD:
                raise TooManyIocsError(
                    f"extraction exceeded MAX_IOCS_PER_PAYLOAD={MAX_IOCS_PER_PAYLOAD}"
                )

    log.info("extraction.completed", count=len(out), defanged=was_defanged)
    return out
