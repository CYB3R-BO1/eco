"""Canonical event types.

These are the only event_type values that may appear in
``investigation_events``. Adding a new type requires updating the Postgres
enum via Alembic migration.
"""
from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    IOC_INGESTED = "IOC_INGESTED"
    IOC_EXTRACTED = "IOC_EXTRACTED"
    IOC_ENRICHED = "IOC_ENRICHED"
    INVESTIGATION_CREATED = "INVESTIGATION_CREATED"
    INVESTIGATION_UPDATED = "INVESTIGATION_UPDATED"
    INVESTIGATION_STATE_CHANGED = "INVESTIGATION_STATE_CHANGED"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"
    EVIDENCE_RECORDED = "EVIDENCE_RECORDED"
    ENRICHMENT_FAILED = "ENRICHMENT_FAILED"
