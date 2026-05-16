"""JSON-walking IOC extraction.

Recursively walks dict/list payloads and runs the text extractor on every
string leaf. The JSON path of each leaf is preserved in the per-IOC metadata
so a downstream investigator can see exactly where in the payload an IOC
originated (`evidence.alerts[2].url`, …).
"""
from __future__ import annotations

from typing import Any

from investigation.extraction.extractor import ExtractedIOC, extract_iocs
from resolution.service import EntityResolutionService
from resolution.types import EntityType


def extract_iocs_from_json(
    payload: Any,
    *,
    types: list[EntityType] | None = None,
    resolver: EntityResolutionService | None = None,
) -> list[ExtractedIOC]:
    resolver = resolver or EntityResolutionService()
    seen: set[tuple[EntityType, str]] = set()
    out: list[ExtractedIOC] = []

    for path, value in _walk(payload):
        if not isinstance(value, str) or not value:
            continue
        for ioc in extract_iocs(value, types=types, resolver=resolver, source_context=path):
            key = (ioc.entity_type, ioc.canonical_form)
            if key in seen:
                continue
            seen.add(key)
            out.append(ioc)
    return out


def _walk(node: Any, path: str = "$") -> list[tuple[str, Any]]:
    if isinstance(node, dict):
        results: list[tuple[str, Any]] = []
        for k, v in node.items():
            results.extend(_walk(v, f"{path}.{k}"))
        return results
    if isinstance(node, list):
        results = []
        for i, v in enumerate(node):
            results.extend(_walk(v, f"{path}[{i}]"))
        return results
    return [(path, node)]
