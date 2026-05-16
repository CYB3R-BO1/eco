"""Variant tracking.

When a user submits `Google.com` and we resolve it to canonical `google.com`,
we record `{"form": "Google.com", "relation": "case_variant"}` on the
EntityAlias.variants JSONB list. The relation tag lets later phases ask
"how did this variant relate to its canonical form?".
"""
from __future__ import annotations

from typing import Any


def make_variant(form: str, relation: str) -> dict[str, Any]:
    """Build a variant entry. ``relation`` should be one of:

    * ``case_variant`` — only differs in letter case
    * ``protocol_stripped`` — input had `http://` / `https://` prefix
    * ``child_url`` — input was a URL whose parent domain is the canonical
    * ``trailing_dot`` — FQDN trailing dot stripped
    * ``defang_refanged`` — defanged input (`hxxp`, `[.]`) restored
    * ``idn_punycode`` — internationalised domain encoded
    * ``other`` — catch-all
    """
    return {"form": form, "relation": relation}


def merge_variants(
    existing: list[dict[str, Any]] | None, new_variant: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return existing variants with ``new_variant`` appended (deduped by form)."""
    existing = list(existing or [])
    if any(v.get("form") == new_variant["form"] for v in existing):
        return existing
    existing.append(new_variant)
    return existing
