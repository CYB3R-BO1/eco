"""Integrity helpers — pure data tests.

The actual graph queries run in the integration test
(``tests/integration/test_graph_correlation.py``). Here we test the
non-query parts: retention thresholds, report shape, has_violations
logic.
"""
from __future__ import annotations

import uuid

from evidence.provenance import ProvenanceLevel
from graph.graph_service.integrity import RETENTION_DAYS, IntegrityReport


def test_retention_days_has_every_provenance_level() -> None:
    for level in ProvenanceLevel:
        assert level in RETENTION_DAYS, level


def test_retention_days_are_positive() -> None:
    for level, days in RETENTION_DAYS.items():
        assert days > 0, (level, days)


def test_retention_ai_generated_shortest() -> None:
    """AI_GENERATED has the lowest reliability, so it stales the fastest.
    USER_SUPPLIED is the longest (raw input from analysts should be
    durable across investigations)."""
    assert RETENTION_DAYS[ProvenanceLevel.AI_GENERATED] < RETENTION_DAYS[ProvenanceLevel.PRIMARY_SOURCE]
    assert RETENTION_DAYS[ProvenanceLevel.AI_GENERATED] <= RETENTION_DAYS[ProvenanceLevel.DERIVED_SOURCE]
    assert RETENTION_DAYS[ProvenanceLevel.USER_SUPPLIED] >= RETENTION_DAYS[ProvenanceLevel.PRIMARY_SOURCE]


def test_empty_report_has_no_violations() -> None:
    r = IntegrityReport(investigation_id=uuid.uuid4())
    assert not r.has_violations


def test_any_section_triggers_violations() -> None:
    iid = uuid.uuid4()
    assert IntegrityReport(investigation_id=iid, orphans=[{"x": 1}]).has_violations
    assert IntegrityReport(investigation_id=iid, cycles=[{"x": 1}]).has_violations
    assert IntegrityReport(investigation_id=iid, confidence_anomalies=[{"x": 1}]).has_violations
    assert IntegrityReport(investigation_id=iid, provenance_gaps=[{"x": 1}]).has_violations
    assert IntegrityReport(investigation_id=iid, stale_enrichments=[{"x": 1}]).has_violations


def test_to_dict_is_json_safe() -> None:
    import json

    r = IntegrityReport(
        investigation_id=uuid.uuid4(),
        orphans=[{"node_id": "abc", "labels": ["IP"]}],
    )
    payload = r.to_dict()
    json.dumps(payload)  # raises if not JSON-safe
    assert payload["has_violations"] is True
    assert payload["orphans"] == [{"node_id": "abc", "labels": ["IP"]}]
