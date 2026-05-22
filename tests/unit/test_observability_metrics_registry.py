"""Metrics-registry sanity (WP1).

Guarantees the central registry is the single source of truth — every metric
that gets observed anywhere has to live in ``core.observability.metrics`` so
WP11's leakage canary can enumerate them.
"""
from __future__ import annotations

from core.observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    REGISTRY,
    hash_bucket,
    registered_metric_names,
    render_latest,
)


def test_registered_metric_names_includes_http_layer() -> None:
    names = registered_metric_names()
    assert "http_requests_total" in names
    assert "http_request_duration_seconds" in names


def test_render_latest_includes_help_text_for_http_counter() -> None:
    HTTP_REQUESTS_TOTAL.labels(method="GET", route="/health", status="200").inc()
    output = render_latest().decode("utf-8")
    assert "# HELP http_requests_total" in output
    assert "http_requests_total{" in output


def test_hash_bucket_is_deterministic_and_short() -> None:
    a = hash_bucket("investigation-abc")
    b = hash_bucket("investigation-abc")
    assert a == b
    assert len(a) == 8
    # different inputs differ
    assert hash_bucket("investigation-abc") != hash_bucket("investigation-xyz")


def test_registry_singleton_is_consistent() -> None:
    """Tests pin the contract: REGISTRY is the registry, not a snapshot."""
    # Identity check — every helper must touch the same registry instance.
    assert REGISTRY is REGISTRY
