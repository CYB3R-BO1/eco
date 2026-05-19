"""Validate an LLM response.

Detects four output-side threat classes:

* **PROMPT_LEAKAGE** — the model echoed parts of its system prompt.
* **PII_DISCLOSURE** — the model produced PII (email, phone, card, AWS key).
* **HIDDEN_INSTRUCTION** — the response contains role tags or instructional
  blocks that, if fed back as input, would constitute an injection.
* **POLICY_VIOLATION** — anything matched by the input pattern catalog
  whose category is unsafe (PROMPT_INJECTION, JAILBREAK, etc.).

The validator runs the input pattern catalog against the response,
filters to the relevant categories, and emits its own signals. Then it
maps the worst category score to PASS / SANITIZE / BLOCK using a fixed
schedule (separate from input policy thresholds because the
risk-tolerance for *outputs* differs from inputs — we're stricter about
PII leaking *out* than coming *in*).
"""
from __future__ import annotations

import time

from core.confidence.propagate import derived_relationship_confidence
from core.security.hashing import sha256_hex
from firewall.analysis import patterns
from firewall.analysis.normalization import normalize
from firewall.models.reports import (
    Redaction,
    ValidationOutcome,
    ValidationReport,
)
from firewall.models.signals import Layer, Signal, ThreatCategory
from firewall.policy.policy import FirewallPolicy
from firewall.sanitization.redactor import apply as apply_sanitization

_OUTPUT_RELEVANT_CATEGORIES = frozenset(
    {
        ThreatCategory.PROMPT_INJECTION,
        ThreatCategory.JAILBREAK,
        ThreatCategory.ROLE_MANIPULATION,
        ThreatCategory.INDIRECT_INJECTION,
        ThreatCategory.TOOL_ABUSE,
        ThreatCategory.DATA_EXFILTRATION,
        ThreatCategory.PII_DISCLOSURE,
    }
)


class OutputValidator:
    def __init__(self, policy: FirewallPolicy) -> None:
        self._policy = policy

    def validate(self, response: str) -> ValidationReport:
        started = time.perf_counter()
        response_fingerprint = sha256_hex(response)
        normalized = normalize(response)

        raw_signals = patterns.detect(normalized.text)
        relevant: list[Signal] = []
        for s in raw_signals:
            category = s.category
            if category in _OUTPUT_RELEVANT_CATEGORIES:
                relevant.append(s)
            elif category is ThreatCategory.PROMPT_LEAKAGE:
                relevant.append(s)

        # Additional output-only detector: hidden instruction tag patterns
        # in *output* are themselves a finding (the model is trying to
        # feed instructions back through itself).
        hidden_instructions = [
            self._reclass(s, ThreatCategory.HIDDEN_INSTRUCTION, Layer.PATTERN)
            for s in raw_signals
            if s.category is ThreatCategory.ROLE_MANIPULATION
        ]
        relevant.extend(hidden_instructions)

        # Classify
        if not relevant:
            result = ValidationOutcome.PASS
            findings: tuple[ThreatCategory, ...] = ()
            sanitized_response: str | None = None
            redactions: tuple[Redaction, ...] = ()
            summary = "PASS — no policy-relevant signals."
        else:
            score, top_category, all_categories = self._score(relevant)
            if score >= 0.80 or top_category in {
                ThreatCategory.DATA_EXFILTRATION,
                ThreatCategory.HIDDEN_INSTRUCTION,
            }:
                result = ValidationOutcome.BLOCK
                summary = (
                    f"BLOCK — output {top_category.value} score {score:.2f}."
                )
                sanitized_response = None
                redactions = ()
            elif score >= 0.40 or any(
                s.category is ThreatCategory.PII_DISCLOSURE for s in relevant
            ):
                result = ValidationOutcome.SANITIZE
                sanitized_response, redactions = apply_sanitization(normalized.text, relevant)
                summary = (
                    f"SANITIZE — output {top_category.value} score {score:.2f}; "
                    f"{len(redactions)} redaction(s)."
                )
            else:
                result = ValidationOutcome.PASS
                sanitized_response = None
                redactions = ()
                summary = (
                    f"PASS — low-severity output signals (score {score:.2f})."
                )
            findings = all_categories

        latency_ms = int((time.perf_counter() - started) * 1000)
        return ValidationReport(
            response_fingerprint=response_fingerprint,
            result=result,
            sanitized_response=sanitized_response,
            findings=findings,
            redactions=redactions,
            signals=tuple(relevant),
            reasoning_summary=summary,
            policy_hash=self._policy.fingerprint(),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _reclass(signal: Signal, category: ThreatCategory, layer: Layer) -> Signal:
        return Signal(
            layer=layer,
            detector_id=f"{signal.detector_id}.output",
            category=category,
            severity=signal.severity,
            weight=signal.weight,
            evidence_span=signal.evidence_span,
            explanation=f"hidden instruction (from {signal.detector_id})",
            rule_id=signal.rule_id,
            pattern_id=signal.pattern_id,
            sanitize=False,
        )

    @staticmethod
    def _score(
        signals: list[Signal],
    ) -> tuple[float, ThreatCategory, tuple[ThreatCategory, ...]]:
        by_cat: dict[ThreatCategory, list[tuple[float, float]]] = {}
        for s in signals:
            by_cat.setdefault(s.category, []).append((s.severity, s.weight))
        cat_scores = {c: derived_relationship_confidence(inp) for c, inp in by_cat.items()}
        top_category = max(cat_scores, key=cat_scores.get)
        score = cat_scores[top_category]
        all_categories = tuple(
            sorted(cat_scores, key=lambda c: -cat_scores[c])
        )
        return score, top_category, all_categories
