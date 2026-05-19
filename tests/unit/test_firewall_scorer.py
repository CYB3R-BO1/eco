"""Risk-scoring invariants.

These tests exercise :func:`firewall.risk.scorer.score` as a pure
function. They are the single source of truth for "given these signals,
what score should we get" so changes to the scoring formula either pass
or fail visibly.
"""
from __future__ import annotations

from firewall.models.signals import Layer, Signal, ThreatCategory
from firewall.policy.policy import FirewallPolicy
from firewall.risk.levels import RiskLevel
from firewall.risk.scorer import score


def _policy() -> FirewallPolicy:
    return FirewallPolicy(
        block_threshold=0.85,
        sanitize_threshold=0.65,
        review_threshold=0.40,
        finding_weight_floor=0.5,
    )


def _signal(severity: float, weight: float = 1.0, cat: ThreatCategory = ThreatCategory.PROMPT_INJECTION) -> Signal:
    return Signal(
        layer=Layer.PATTERN,
        detector_id="test",
        category=cat,
        severity=severity,
        weight=weight,
    )


def test_no_signals_means_safe() -> None:
    r = score([], _policy())
    assert r.risk_score == 0.0
    assert r.risk_level is RiskLevel.SAFE


def test_single_strong_signal_uses_its_severity() -> None:
    r = score([_signal(0.9)], _policy())
    assert r.risk_score == 0.9
    assert r.risk_level is RiskLevel.MALICIOUS


def test_two_weak_corroborating_signals_lift_floor_but_cap_at_max() -> None:
    r = score(
        [_signal(0.3, 0.5), _signal(0.6, 0.5)],
        _policy(),
    )
    # weighted mean = 0.45, max = 0.6 → score = min(0.45, 0.6) = 0.45
    assert 0.40 <= r.risk_score <= 0.60
    assert r.risk_score <= 0.6


def test_worst_category_wins() -> None:
    r = score(
        [
            _signal(0.5, 1.0, ThreatCategory.OTHER),
            _signal(0.9, 1.0, ThreatCategory.DATA_EXFILTRATION),
        ],
        _policy(),
    )
    assert r.risk_score == 0.9
    assert ThreatCategory.DATA_EXFILTRATION in r.classifications


def test_classifications_sorted_by_descending_score() -> None:
    r = score(
        [
            _signal(0.3, 1.0, ThreatCategory.OTHER),
            _signal(0.9, 1.0, ThreatCategory.JAILBREAK),
            _signal(0.6, 1.0, ThreatCategory.ROLE_MANIPULATION),
        ],
        _policy(),
    )
    # Order should be JAILBREAK > ROLE_MANIPULATION > OTHER (OTHER below
    # 0.2 cutoff is excluded; here it's 0.3 so included).
    assert r.classifications[0] is ThreatCategory.JAILBREAK


def test_below_cutoff_classifications_dropped() -> None:
    r = score([_signal(0.05, 1.0, ThreatCategory.OTHER)], _policy())
    assert r.classifications == ()
