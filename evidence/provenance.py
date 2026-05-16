"""Provenance levels and source-reliability constants.

PLAN.md §3 defines five provenance tiers. ``SOURCE_RELIABILITY`` is the
authoritative lookup used by ``EvidenceStore`` and the enrichment executor
when constructing Evidence rows. Adding a provider means adding an entry
here — no inline magic numbers elsewhere.
"""
from __future__ import annotations

from enum import Enum


class ProvenanceLevel(str, Enum):
    PRIMARY_SOURCE = "PRIMARY_SOURCE"   # direct observation (DNS, VirusTotal report)
    DERIVED_SOURCE = "DERIVED_SOURCE"   # calculated from primary (correlation)
    AI_GENERATED = "AI_GENERATED"       # agent finding, narrative summary
    THIRD_PARTY = "THIRD_PARTY"         # external reference (blog, feed)
    USER_SUPPLIED = "USER_SUPPLIED"     # end-user input


SOURCE_RELIABILITY: dict[str, float] = {
    "VirusTotal": 0.95,
    "WHOIS": 0.90,
    "DNS": 0.95,
    "GeoIP": 0.85,
    "internal_extraction": 0.95,
    "user_supplied": 0.50,
}


def reliability_for(source: str) -> float:
    """Return the reliability for a known source; default 0.50 for unknown sources."""
    return SOURCE_RELIABILITY.get(source, 0.50)
