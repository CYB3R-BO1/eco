"""Rule evaluator.

``RulesEngine.evaluate(normalization, prior_signals)`` walks the
:data:`firewall.rules.catalog.RULES` tuple and emits a :class:`Signal`
for each rule whose conditions are satisfied. Rule signals carry the
rule's own severity/weight — the scorer sees them alongside layer-1–3
signals and aggregates by category.

A rule's emitted signal has its ``layer`` set to ``Layer.RULE`` and its
``rule_id`` set so the explainability payload can link back to the
catalog entry. Critical-band rules also pass ``metadata={"critical":
True}`` so the policy engine can short-circuit to BLOCK regardless of
the aggregate score.
"""
from __future__ import annotations

from firewall.analysis.normalization import NormalizationResult
from firewall.models.signals import Layer, Severity, Signal
from firewall.rules.catalog import RULES, RuleDefinition


class RulesEngine:
    def __init__(self, rules: tuple[RuleDefinition, ...] | None = None) -> None:
        self._rules = rules if rules is not None else RULES

    def evaluate(
        self,
        normalization: NormalizationResult,
        prior_signals: list[Signal],
    ) -> list[Signal]:
        pattern_ids = {s.pattern_id for s in prior_signals if s.pattern_id}
        fired: list[Signal] = []
        for rule in self._rules:
            if not self._matches(rule, normalization, pattern_ids):
                continue
            fired.append(
                Signal(
                    layer=Layer.RULE,
                    detector_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    weight=rule.weight,
                    explanation=rule.description,
                    rule_id=rule.rule_id,
                    sanitize=rule.sanitize,
                    metadata={
                        "severity_band": rule.severity_band.value,
                        "critical": rule.severity_band is Severity.CRITICAL,
                        "references": list(rule.references),
                    },
                )
            )
        return fired

    @staticmethod
    def _matches(
        rule: RuleDefinition,
        normalization: NormalizationResult,
        pattern_ids: set[str],
    ) -> bool:
        if rule.required_patterns and not all(
            pid in pattern_ids for pid in rule.required_patterns
        ):
            return False
        if rule.any_patterns and not any(pid in pattern_ids for pid in rule.any_patterns):
            return False
        if rule.heuristic_predicates and not any(
            predicate(normalization) for predicate in rule.heuristic_predicates
        ):
            return False
        return True
