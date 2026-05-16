from __future__ import annotations

import pytest

from core.confidence.propagate import derived_confidence


def test_returns_minimum() -> None:
    assert derived_confidence(0.95, 0.99, 0.85) == 0.85


def test_single_score() -> None:
    assert derived_confidence(0.42) == 0.42


def test_rejects_empty() -> None:
    with pytest.raises(ValueError):
        derived_confidence()


def test_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        derived_confidence(1.5)
    with pytest.raises(ValueError):
        derived_confidence(-0.1)


def test_zero_is_legal() -> None:
    assert derived_confidence(0.0, 0.9) == 0.0
