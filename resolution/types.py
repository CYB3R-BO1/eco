"""Entity / IOC type taxonomy.

Used by Entity Resolution, IOC Extraction, and ORM models. Defined in its own
module so ORM models can import it without pulling in the rest of
``resolution/`` (which has cycles otherwise).
"""
from __future__ import annotations

from enum import Enum


class EntityType(str, Enum):
    """The set of IOC / entity kinds the platform recognises in Phase 2."""

    DOMAIN = "domain"
    URL = "url"
    IP = "ip"
    EMAIL = "email"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    CVE = "cve"
    RAW_LOG = "raw_log"
    JSON_PAYLOAD = "json_payload"
