"""Payload validators for ingestion.

Phase 2 accepts:
* a plain string (URL, domain, IP, hash, email, or raw log blob),
* a JSON dict (arbitrary structure; IOCs found via json_walker), or
* an explicit ``type`` hint that pins how the artifact is treated.
"""
from __future__ import annotations

from typing import Any

from resolution.types import EntityType

MAX_ARTIFACT_BYTES = 10 * 1024 * 1024  # 10 MB


class IngestValidationError(ValueError):
    pass


def validate_payload(
    artifact: str | dict[str, Any] | list[Any],
    declared_type: EntityType | None,
) -> None:
    if artifact is None:
        raise IngestValidationError("artifact required")
    if isinstance(artifact, str):
        if not artifact.strip():
            raise IngestValidationError("artifact must be non-empty")
        if len(artifact.encode("utf-8")) > MAX_ARTIFACT_BYTES:
            raise IngestValidationError("artifact exceeds 10MB limit")
    elif isinstance(artifact, (dict, list)):
        # Bound via str() to roughly approximate serialized size.
        if len(str(artifact)) > MAX_ARTIFACT_BYTES:
            raise IngestValidationError("artifact exceeds 10MB limit")
    else:
        raise IngestValidationError(f"unsupported artifact type: {type(artifact).__name__}")

    if declared_type is not None and declared_type not in EntityType:
        raise IngestValidationError(f"unknown declared type: {declared_type}")
