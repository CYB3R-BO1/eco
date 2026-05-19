"""Policy engine — turn an AnalysisReport into a single FirewallAction.

Pure function. The decision rule:

1. If any signal carries ``metadata["critical"] == True`` (i.e. a
   Severity.CRITICAL rule fired), action = BLOCK regardless of score.
2. Else, derive from the numeric score:
   * score ≥ block_threshold       → BLOCK
   * score ≥ sanitize_threshold    → SANITIZE
   * score ≥ review_threshold      → REQUIRE_REVIEW
   * otherwise                     → ALLOW
3. Whatever the verdict, attach the full explainability payload so the
   caller (or an auditor) can see exactly why.

The reasoning summary is templated — no LLM in the loop. That's
deliberate: reasoning text that drifts under model nondeterminism makes
audits unfalsifiable.
"""
from __future__ import annotations

from firewall.models.reports import AnalysisReport, Explainability
from firewall.policy.actions import FirewallAction
from firewall.policy.policy import FirewallPolicy


class PolicyEngine:
    def __init__(self, policy: FirewallPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> FirewallPolicy:
        return self._policy

    def decide(self, report: AnalysisReport) -> tuple[FirewallAction, Explainability]:
        critical_rule_ids = tuple(
            s.rule_id for s in report.signals
            if s.metadata.get("critical") and s.rule_id
        )
        if critical_rule_ids:
            action = FirewallAction.BLOCK
            reasoning = (
                f"BLOCKED on critical rule(s): {', '.join(critical_rule_ids)}. "
                f"Score {report.risk_score:.2f} ({report.risk_level.value})."
            )
        else:
            score = report.risk_score
            if score >= self._policy.block_threshold:
                action = FirewallAction.BLOCK
                reasoning = (
                    f"BLOCKED — score {score:.2f} ≥ block threshold "
                    f"{self._policy.block_threshold:.2f}."
                )
            elif score >= self._policy.sanitize_threshold:
                action = FirewallAction.SANITIZE
                reasoning = (
                    f"SANITIZE — score {score:.2f} in "
                    f"[{self._policy.sanitize_threshold:.2f}, {self._policy.block_threshold:.2f})."
                )
            elif score >= self._policy.review_threshold:
                action = FirewallAction.REQUIRE_REVIEW
                reasoning = (
                    f"REVIEW — score {score:.2f} in "
                    f"[{self._policy.review_threshold:.2f}, {self._policy.sanitize_threshold:.2f})."
                )
            else:
                action = FirewallAction.ALLOW
                reasoning = (
                    f"ALLOW — score {score:.2f} below review threshold "
                    f"{self._policy.review_threshold:.2f}."
                )

        explainability = Explainability(
            matched_rules=tuple(
                sorted({s.rule_id for s in report.signals if s.rule_id})
            ),
            triggered_patterns=tuple(
                sorted({s.pattern_id for s in report.signals if s.pattern_id})
            ),
            reasoning_summary=reasoning,
            policy_hash=self._policy.fingerprint(),
            policy_references=self._policy.references,
        )
        return action, explainability
