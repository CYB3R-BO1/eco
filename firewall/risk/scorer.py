"""Layer 6 — risk scoring.

Aggregates the full Signal list into a single risk_score ∈ [0, 1] plus
the implicated :class:`firewall.models.signals.ThreatCategory` set.

Per Phase 4 plan §"Risk scoring — exact formula":

1. Group signals by category.
2. Within a category, combine ``(severity, weight)`` pairs via
   :func:`core.confidence.propagate.derived_relationship_confidence`. This
   keeps the corroboration discipline from Phase 3 graph confidence —
   multiple low-severity hits in the same category lift the floor but
   never exceed the strongest single hit.
3. Final risk_score = ``max(category_scores)``. Worst category wins; we
   don't *add* across categories because that would over-penalize prompts
   that hit two weak, unrelated detectors.
4. RiskLevel is derived from the score via the policy thresholds.

Pure function — no I/O, no logging. Same inputs always produce same
output. That property is the centerpiece of the explainability contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.confidence.propagate import derived_relationship_confidence
from firewall.models.signals import Signal, ThreatCategory
from firewall.policy.policy import FirewallPolicy
from firewall.risk.levels import RiskLevel


@dataclass(frozen=True)
class ScoreResult:
    risk_score: float
    risk_level: RiskLevel
    classifications: tuple[ThreatCategory, ...]
    category_scores: dict[ThreatCategory, float]


def score(signals: list[Signal], policy: FirewallPolicy) -> ScoreResult:
    if not signals:
        return ScoreResult(
            risk_score=0.0,
            risk_level=RiskLevel.SAFE,
            classifications=(),
            category_scores={},
        )

    by_category: dict[ThreatCategory, list[tuple[float, float]]] = {}
    for s in signals:
        by_category.setdefault(s.category, []).append((s.severity, s.weight))

    category_scores: dict[ThreatCategory, float] = {}
    for cat, scored_inputs in by_category.items():
        category_scores[cat] = derived_relationship_confidence(scored_inputs)

    final = max(category_scores.values())
    # Classifications: every category whose score exceeds a low cutoff —
    # we want even mild signals to surface in the audit payload so the
    # analyst sees the full picture, not just the top category.
    classifications = tuple(
        sorted(
            (cat for cat, val in category_scores.items() if val >= 0.20),
            key=lambda c: -category_scores[c],
        )
    )
    return ScoreResult(
        risk_score=final,
        risk_level=policy.risk_level_for(final),
        classifications=classifications,
        category_scores=category_scores,
    )
