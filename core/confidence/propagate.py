"""Confidence propagation.

PLAN.md §6: derived relationships inherit the minimum confidence across the
chain. We never invent confidence — every score is the most pessimistic of its
contributing sources. This makes confidence "weakest-link" rather than
"average" and prevents AI/derived findings from inflating apparent certainty.
"""
from __future__ import annotations


def derived_confidence(*scores: float) -> float:
    """Return the minimum of all provided scores.

    Raises ValueError on empty input — silently defaulting (e.g., to 1.0)
    would hide bugs where a caller forgot to thread its source confidence
    through. Each score must be in [0.0, 1.0].
    """
    if not scores:
        raise ValueError("derived_confidence requires at least one score")
    for s in scores:
        if not 0.0 <= s <= 1.0:
            raise ValueError(f"confidence score out of range [0,1]: {s}")
    return min(scores)
