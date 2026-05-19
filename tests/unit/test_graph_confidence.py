"""Weighted relationship-confidence propagation."""
from __future__ import annotations

import pytest

from core.confidence.propagate import (
    derived_confidence,
    derived_relationship_confidence,
)


def test_strict_min_still_works() -> None:
    """The new function does not break the old contract."""
    assert derived_confidence(0.9, 0.6) == 0.6


def test_weighted_with_single_input_returns_input_confidence() -> None:
    assert derived_relationship_confidence([(0.7, 1.0)]) == pytest.approx(0.7)


def test_weighted_corroboration_lifts_above_weakest() -> None:
    """Two equally weighted inputs (0.9, 0.6) → weighted mean 0.75 — the
    strict-min function would say 0.6."""
    out = derived_relationship_confidence([(0.9, 1.0), (0.6, 1.0)])
    assert out == pytest.approx(0.75)


def test_weighted_never_exceeds_max_input() -> None:
    """If both inputs corroborate at high confidence, the result is
    capped by the best single source."""
    out = derived_relationship_confidence([(0.95, 2.0), (0.90, 1.0)])
    assert out <= 0.95


def test_weighted_rejects_empty() -> None:
    with pytest.raises(ValueError):
        derived_relationship_confidence([])


def test_weighted_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError):
        derived_relationship_confidence([(1.1, 1.0)])
    with pytest.raises(ValueError):
        derived_relationship_confidence([(-0.1, 1.0)])


def test_weighted_rejects_negative_weight() -> None:
    with pytest.raises(ValueError):
        derived_relationship_confidence([(0.5, -1.0)])


def test_weighted_zero_weights_falls_back_to_strict_min() -> None:
    """If all weights are zero (degenerate input), the result must not
    silently be 1.0 — it falls back to the strict-min so a missing
    weight signal cannot inflate confidence."""
    out = derived_relationship_confidence([(0.9, 0.0), (0.4, 0.0)])
    assert out == 0.4
