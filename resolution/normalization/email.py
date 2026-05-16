"""Email normalization.

Lowercase the entire address. We intentionally do NOT do provider-specific
quirks (e.g. Gmail dot-stripping) — that would mis-canonicalize addresses
that legitimately differ for some providers, and the semantic question
"are these the same person?" isn't one extraction can answer.
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}$"
)


def normalize_email(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("email must be a non-empty string")
    value = raw.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError(f"invalid email: {raw!r}")
    return value
