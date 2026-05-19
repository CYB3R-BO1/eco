"""Cross-cutting security utilities shared by every layer of the platform.

Currently exports ``sha256_hex`` — the canonical content-fingerprinting helper
used by the firewall to identify prompts and responses without storing the
raw text (CLAUDE.md invariant #12).
"""
from __future__ import annotations

from core.security.hashing import sha256_hex

__all__ = ["sha256_hex"]
