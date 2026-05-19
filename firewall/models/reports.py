"""Outputs of each firewall stage.

Three concentric containers:

* :class:`AnalysisReport` — what the pipeline returns. No decision yet.
* :class:`Decision`       — what the policy engine returns. Has a single
                            :class:`firewall.policy.actions.FirewallAction`.
* :class:`ValidationReport` — what output-validation returns. Distinct from
                              ``Decision`` because the action vocabulary is
                              PASS / SANITIZE / BLOCK (no REQUIRE_REVIEW —
                              output validation is end-of-pipeline).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from firewall.models.signals import Signal, ThreatCategory
from firewall.policy.actions import FirewallAction
from firewall.risk.levels import RiskLevel


@dataclass(frozen=True)
class Redaction:
    """A single edit applied by the sanitizer.

    Offsets refer to the **normalized** prompt (post layer 1). Replacements
    are deterministic — the sanitizer never invents content, only
    substitutes a fixed marker.
    """

    start: int
    end: int
    rule_id: str
    replacement: str
    reason: str


@dataclass(frozen=True)
class Explainability:
    matched_rules: tuple[str, ...]
    triggered_patterns: tuple[str, ...]
    reasoning_summary: str
    policy_hash: str
    policy_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisReport:
    prompt_fingerprint: str
    prompt_length: int
    normalized_length: int
    risk_score: float
    risk_level: RiskLevel
    classifications: tuple[ThreatCategory, ...]
    signals: tuple[Signal, ...]
    explainability: Explainability
    latency_ms: int
    llm_classifier_available: bool = False
    truncated: bool = False


@dataclass(frozen=True)
class Decision:
    analysis: AnalysisReport
    action: FirewallAction
    sanitized_prompt: str | None
    redactions: tuple[Redaction, ...]
    explainability: Explainability


class ValidationOutcome(str, Enum):
    PASS = "PASS"
    SANITIZE = "SANITIZE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ValidationReport:
    response_fingerprint: str
    result: ValidationOutcome
    sanitized_response: str | None
    findings: tuple[ThreatCategory, ...]
    redactions: tuple[Redaction, ...]
    signals: tuple[Signal, ...]
    reasoning_summary: str
    policy_hash: str
    latency_ms: int
