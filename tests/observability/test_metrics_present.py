"""Phase 6 WP11 — every declared metric is reachable via /metrics.

Pins the registry contract: if a metric is declared in
``core.observability.metrics`` it MUST be visible in the Prometheus
text-format exposition. Stops accidental removals from going unnoticed
(silent loss of operational visibility is the highest-cost regression
this module can catch).
"""
from __future__ import annotations

from core.observability.metrics import registered_metric_names, render_latest


def test_render_latest_exposes_every_declared_metric() -> None:
    text = render_latest().decode("utf-8")
    for name in registered_metric_names():
        # Counters get a ``_total`` suffix in the exposition format, but
        # the HELP line always includes the base name verbatim. Grep for
        # it.
        assert f"# HELP {name}" in text, f"metric missing from /metrics: {name}"


def test_no_duplicate_metric_declarations() -> None:
    """The single-registry contract: no metric registered twice."""
    names = registered_metric_names()
    assert len(names) == len(set(names))
