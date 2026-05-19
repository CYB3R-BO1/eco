"""Content fingerprinting.

CLAUDE.md invariant #12 says we hash prompts for logs — we never store the
raw text. ``sha256_hex`` is the single canonical helper for that hash. It
accepts ``str`` (encoded as UTF-8) or ``bytes`` and returns the 64-character
lowercase hex digest. Callers should treat the digest as opaque — it's a
join key between Postgres audit rows and graph Prompt nodes, not a security
primitive on its own.
"""
from __future__ import annotations

import hashlib


def sha256_hex(content: str | bytes) -> str:
    """Return the SHA-256 hex digest of ``content``.

    ``str`` inputs are encoded as UTF-8 first. The output is always a
    64-character lowercase hex string.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()
