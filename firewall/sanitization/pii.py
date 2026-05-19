"""PII detection helpers used directly by the output validator.

The input-side firewall picks up PII via the pattern catalog
(``p.pii.*``) which is shared with sanitization. The output validator
re-uses the same compiled regexes but emits ``ValidationOutcome``-
shaped signals. Keeping the regex constants here means there's one
source of truth for what counts as PII in this codebase.
"""
from __future__ import annotations

import re

# Re-exported from the pattern catalog for clarity (one source of truth).
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
PHONE_RE = re.compile(r"\+[1-9]\d{1,14}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def contains_pii(text: str) -> bool:
    return bool(
        EMAIL_RE.search(text)
        or AWS_KEY_RE.search(text)
        or PHONE_RE.search(text)
        or CREDIT_CARD_RE.search(text)
    )
