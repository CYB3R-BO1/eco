"""Regex patterns for IOC extraction.

Carefully bounded to avoid catastrophic backtracking. ``refang()`` undoes
common analyst-defanging conventions before any regex runs, so a defanged
sample like `hxxp://malicious[.]com` matches the URL pattern after a single
pass of substitution.
"""
from __future__ import annotations

import re

from resolution.types import EntityType

# Defang reversals: applied left-to-right, before pattern matching.
_REFANG_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bhxxps?://", re.IGNORECASE), "http://"),
    (re.compile(r"\bhxxp://", re.IGNORECASE), "http://"),
    (re.compile(r"\[\.\]"), "."),
    (re.compile(r"\(\.\)"), "."),
    (re.compile(r"\[dot\]", re.IGNORECASE), "."),
    (re.compile(r"\(dot\)", re.IGNORECASE), "."),
    (re.compile(r"\[@\]"), "@"),
    (re.compile(r"\(at\)", re.IGNORECASE), "@"),
    (re.compile(r"\[at\]", re.IGNORECASE), "@"),
)


def refang(text: str) -> str:
    """Reverse common defang conventions in ``text``."""
    for pattern, replacement in _REFANG_SUBS:
        text = pattern.sub(replacement, text)
    return text


# IOC patterns — match on refanged text only.
URL_RE = re.compile(
    r"\bhttps?://[A-Za-z0-9._\-]+(?:\.[A-Za-z]{2,63})(?::\d{1,5})?(?:/[^\s<>\"']*)?",
)
DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,5}(?:com|org|net|gov|edu|io|ai|co|us|uk|de|fr|cn|ru|jp|info|xyz|biz|dev|app|cloud|tech|me|tv|mil)\b",
    re.IGNORECASE,
)
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b"
)
IPV6_RE = re.compile(
    r"\b(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}\b|"
    r"\b(?:[A-Fa-f0-9]{1,4}:){1,7}:(?:[A-Fa-f0-9]{1,4}:){0,6}[A-Fa-f0-9]{0,4}\b"
)
HASH_MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
HASH_SHA1_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
HASH_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}\b"
)
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b")


# Order matters: longer-hash patterns first so SHA256 isn't shadowed by SHA1/MD5.
PATTERNS: tuple[tuple[EntityType, re.Pattern[str]], ...] = (
    (EntityType.URL, URL_RE),
    (EntityType.EMAIL, EMAIL_RE),
    (EntityType.HASH_SHA256, HASH_SHA256_RE),
    (EntityType.HASH_SHA1, HASH_SHA1_RE),
    (EntityType.HASH_MD5, HASH_MD5_RE),
    (EntityType.IP, IPV6_RE),
    (EntityType.IP, IPV4_RE),
    (EntityType.CVE, CVE_RE),
    (EntityType.DOMAIN, DOMAIN_RE),
)
