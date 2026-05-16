"""Pure normalization functions — no DB writes.

Used by the stateless ``POST /iocs/extract`` endpoint (which canonicalizes
without persisting) and by :class:`resolution.service.EntityResolutionService`
(which canonicalizes and then persists). Keep these strictly side-effect-free.
"""
from resolution.normalization.domain import normalize_domain
from resolution.normalization.email import normalize_email
from resolution.normalization.hash import normalize_hash
from resolution.normalization.ip import normalize_ip
from resolution.normalization.url import normalize_url, parent_domain

__all__ = [
    "normalize_domain",
    "normalize_email",
    "normalize_hash",
    "normalize_ip",
    "normalize_url",
    "parent_domain",
]
