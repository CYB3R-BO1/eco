"""URL normalization.

Canonicalize scheme + host case, strip the fragment, leave the path/query
mostly alone (they're often the discriminating part of an IOC). Whatever
goes in here, the parent domain comes out via :func:`parent_domain` so the
ER layer can record a `child_url` variant.
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from resolution.normalization.domain import normalize_domain


def normalize_url(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("url must be a non-empty string")
    parsed = urlparse(raw.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid url (missing scheme or netloc): {raw!r}")
    netloc = parsed.netloc.lower()
    scheme = parsed.scheme.lower()
    return urlunparse((scheme, netloc, parsed.path or "", parsed.params, parsed.query, ""))


def parent_domain(url: str) -> str:
    """Return the bare domain portion of a normalized URL."""
    parsed = urlparse(url)
    host = parsed.netloc.split("@", 1)[-1].split(":", 1)[0]
    return normalize_domain(host)
