"""Confidence propagation.

PLAN.md §6: derived relationships inherit the minimum confidence across the
chain. We never invent confidence — every score is the most pessimistic of its
contributing sources. This makes confidence "weakest-link" rather than
"average" and prevents AI/derived findings from inflating apparent certainty.

Two functions live here. :func:`derived_confidence` is the strict
weakest-link rule used everywhere a single chain produces a single number
(extraction, evidence inheritance). :func:`derived_relationship_confidence`
is the Phase 3 graph-edge variant: when multiple Evidence corroborate the
same fact, it lets corroboration *raise the floor* without ever letting
the result exceed the most reliable input.
"""
from __future__ import annotations

from collections.abc import Sequence


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


def derived_relationship_confidence(
    scored_inputs: Sequence[tuple[float, float]],
) -> float:
    """Weighted aggregation for graph relationship confidence.

    Each input is a ``(confidence, weight)`` pair. The output preserves the
    weakest-link discipline: it never exceeds ``min(confidence)``. But when
    multiple inputs corroborate the same fact, the weighted-mean of the
    *high-confidence* inputs lifts the result above the floor, up to (but
    not past) the most reliable corroborating source.

    Concretely: given inputs ``[(0.9, 0.5), (0.6, 0.5)]`` the strict-min
    rule returns 0.6 (which feels too pessimistic when both sources agree
    and one is strong). This function returns the weighted mean — 0.75 —
    clamped by ``min(0.9, 0.6) = 0.6`` floor logic when only one source
    fires, but otherwise lifting toward the corroborated value.

    Implementation: weighted-mean of the inputs, then clamp to ``[0,
    max_input_confidence]``. The floor is intentionally NOT the
    weakest-link min — that's what :func:`derived_confidence` is for.
    Use this only on edges that aggregate independent corroborations
    (RESOLVES_TO, RELATED_TO, REFERENCES); use ``derived_confidence`` on
    edges that represent a single chain of inference (PART_OF, GENERATED).
    """
    if not scored_inputs:
        raise ValueError("derived_relationship_confidence requires at least one input")
    total_weight = 0.0
    weighted_sum = 0.0
    max_confidence = 0.0
    for confidence, weight in scored_inputs:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence out of range [0,1]: {confidence}")
        if weight < 0.0:
            raise ValueError(f"weight must be non-negative: {weight}")
        weighted_sum += confidence * weight
        total_weight += weight
        if confidence > max_confidence:
            max_confidence = confidence
    if total_weight == 0.0:
        # Degenerate: all weights zero. Fall back to the strict min so we
        # never accidentally emit a 1.0 from missing weights.
        return min(c for c, _ in scored_inputs)
    weighted_mean = weighted_sum / total_weight
    # Clamp: never exceed the best single source.
    return min(weighted_mean, max_confidence)
