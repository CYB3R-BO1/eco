"""Phase 6 WP2 — every declared domain metric is present in the registry.

If a future refactor removes a metric, this test fails — that's the
intent. Prevents silent loss of operational visibility.
"""
from __future__ import annotations

import pytest

from core.observability.metrics import (
    depth_bucket,
    registered_metric_names,
    risk_bucket,
)

EXPECTED_METRICS = {
    # WP1
    "http_requests_total",
    "http_request_duration_seconds",
    # WP2 — graph
    "ai_security_graph_traversal_duration_seconds",
    "ai_security_graph_writes_total",
    "ai_security_graph_relationships",
    # enrichment
    "ai_security_enrichment_total",
    # firewall
    "ai_security_firewall_decisions_total",
    "ai_security_firewall_pipeline_duration_seconds",
    # workflows/agents
    "ai_security_workflow_duration_seconds",
    "ai_security_workflow_active",
    "ai_security_agent_run_duration_seconds",
    "ai_security_agent_retries_total",
    "ai_security_circuit_breaker_state",
    # LLM
    "ai_security_llm_tokens_used_total",
    # DLQ + memory
    "ai_security_dlq_depth",
    "ai_security_memory_tokens_in_use",
    # WP6 surface (declared here so the contract is one place)
    "ai_security_retention_job_runs_total",
    # WP3 — auth denials
    "auth_denials_total",
    # WP4 — RBAC denials
    "permission_denials_total",
}


def test_all_expected_metrics_are_registered() -> None:
    names = set(registered_metric_names())
    missing = EXPECTED_METRICS - names
    assert not missing, f"metrics missing from registry: {sorted(missing)}"


def test_no_unexpected_metrics_polluting_registry() -> None:
    """Catch accidental duplicate registrations from unrelated modules."""
    names = set(registered_metric_names())
    extras = names - EXPECTED_METRICS
    assert not extras, f"unexpected metrics in registry: {sorted(extras)}"


@pytest.mark.parametrize(
    "depth,bucket",
    [(0, "1"), (1, "1"), (2, "2"), (3, "3-4"), (4, "3-4"), (5, "5-8"), (8, "5-8"), (9, "9+")],
)
def test_depth_bucket(depth: int, bucket: str) -> None:
    assert depth_bucket(depth) == bucket


@pytest.mark.parametrize(
    "risk,bucket",
    [
        (0.0, "low"),
        (0.19, "low"),
        (0.20, "guarded"),
        (0.39, "guarded"),
        (0.40, "elevated"),
        (0.64, "elevated"),
        (0.65, "high"),
        (0.84, "high"),
        (0.85, "critical"),
        (1.0, "critical"),
    ],
)
def test_risk_bucket(risk: float, bucket: str) -> None:
    assert risk_bucket(risk) == bucket
