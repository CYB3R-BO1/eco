"""Policy-engine decision boundaries.

The four cutoffs (review=0.40, sanitize=0.65, block=0.85) are tested
directly. A critical-severity rule short-circuits to BLOCK regardless of
score.
"""
from __future__ import annotations

from firewall.models.reports import AnalysisReport, Explainability
from firewall.models.signals import Layer, Signal, ThreatCategory
from firewall.policy.actions import FirewallAction
from firewall.policy.engine import PolicyEngine
from firewall.policy.policy import FirewallPolicy
from firewall.risk.levels import RiskLevel


def _policy() -> FirewallPolicy:
    return FirewallPolicy(
        block_threshold=0.85,
        sanitize_threshold=0.65,
        review_threshold=0.40,
        finding_weight_floor=0.5,
    )


def _report(score: float, level: RiskLevel, signals: tuple[Signal, ...] = ()) -> AnalysisReport:
    return AnalysisReport(
        prompt_fingerprint="0" * 64,
        prompt_length=10,
        normalized_length=10,
        risk_score=score,
        risk_level=level,
        classifications=(),
        signals=signals,
        explainability=Explainability(
            matched_rules=(),
            triggered_patterns=(),
            reasoning_summary="",
            policy_hash="abc",
        ),
        latency_ms=1,
    )


def test_allow_below_review() -> None:
    p = _policy()
    action, _ = PolicyEngine(p).decide(_report(0.10, RiskLevel.SAFE))
    assert action is FirewallAction.ALLOW


def test_review_at_review_threshold() -> None:
    p = _policy()
    action, _ = PolicyEngine(p).decide(_report(0.40, RiskLevel.SUSPICIOUS))
    assert action is FirewallAction.REQUIRE_REVIEW


def test_sanitize_at_sanitize_threshold() -> None:
    p = _policy()
    action, _ = PolicyEngine(p).decide(_report(0.65, RiskLevel.HIGH_RISK))
    assert action is FirewallAction.SANITIZE


def test_block_at_block_threshold() -> None:
    p = _policy()
    action, _ = PolicyEngine(p).decide(_report(0.85, RiskLevel.MALICIOUS))
    assert action is FirewallAction.BLOCK


def test_critical_rule_forces_block_even_at_low_score() -> None:
    critical_signal = Signal(
        layer=Layer.RULE,
        detector_id="r.injection.confirmed",
        category=ThreatCategory.PROMPT_INJECTION,
        severity=0.5,
        weight=1.0,
        rule_id="r.injection.confirmed",
        metadata={"critical": True, "severity_band": "critical"},
    )
    p = _policy()
    action, exp = PolicyEngine(p).decide(_report(0.10, RiskLevel.SAFE, (critical_signal,)))
    assert action is FirewallAction.BLOCK
    assert "r.injection.confirmed" in exp.matched_rules


def test_policy_hash_is_stable() -> None:
    p1 = _policy()
    p2 = _policy()
    assert p1.fingerprint() == p2.fingerprint()


def test_policy_thresholds_must_be_ordered() -> None:
    import pytest
    with pytest.raises(ValueError):
        FirewallPolicy(
            block_threshold=0.5,
            sanitize_threshold=0.7,
            review_threshold=0.3,
            finding_weight_floor=0.5,
        )
