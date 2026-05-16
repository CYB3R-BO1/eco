"""Hash normalization.

Lowercase hex + length validation. Returns the (normalized, type) tuple so
callers know which hash family they're holding without re-measuring.
"""
from __future__ import annotations

import re

from resolution.types import EntityType

_HEX_RE = re.compile(r"^[a-f0-9]+$")
_LENGTHS = {
    32: EntityType.HASH_MD5,
    40: EntityType.HASH_SHA1,
    64: EntityType.HASH_SHA256,
}


def normalize_hash(raw: str) -> tuple[str, EntityType]:
    if not isinstance(raw, str) or not raw:
        raise ValueError("hash must be a non-empty string")
    value = raw.strip().lower()
    if not _HEX_RE.match(value):
        raise ValueError(f"hash must be hex: {raw!r}")
    if len(value) not in _LENGTHS:
        raise ValueError(f"unrecognised hash length {len(value)}: {raw!r}")
    return value, _LENGTHS[len(value)]
