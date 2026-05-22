"""Six-layer prompt analysis pipeline orchestrator.

Stitches the layer modules together into a single ``analyze`` coroutine.
Deterministic layers (1–4) run synchronously inside an executor-friendly
function so the whole pipeline can be wrapped in ``asyncio.wait_for``
with the timeout configured in :class:`core.config.settings.FirewallSettings`.
Layer 5 (LLM classifier) runs through whatever
:class:`firewall.analysis.llm_classifier.LLMClassifierProtocol` the
caller injected — Phase 4 uses :class:`NullClassifier`.

Always returns an :class:`AnalysisReport`. The only way to surface a
failure is through the report's ``llm_classifier_available`` flag and
the explainability summary; the analysis layers themselves never raise
on prompt content.
"""
from __future__ import annotations

import asyncio
import time

from core.observability.metrics import (
    FIREWALL_PIPELINE_DURATION_SECONDS,
    time_histogram,
)
from core.security.hashing import sha256_hex
from firewall.analysis import heuristics, normalization, patterns
from firewall.analysis.llm_classifier import LLMClassifierProtocol, NullClassifier
from firewall.models.reports import AnalysisReport, Explainability
from firewall.models.signals import Signal
from firewall.policy.policy import FirewallPolicy
from firewall.risk.scorer import score
from firewall.rules.engine import RulesEngine


class PromptAnalysisPipeline:
    def __init__(
        self,
        *,
        policy: FirewallPolicy,
        rules_engine: RulesEngine | None = None,
        llm_classifier: LLMClassifierProtocol | None = None,
        detection_timeout_ms: int = 2_000,
    ) -> None:
        self._policy = policy
        self._rules = rules_engine or RulesEngine()
        self._llm = llm_classifier or NullClassifier()
        self._timeout_s = detection_timeout_ms / 1_000.0

    async def analyze(self, prompt: str) -> AnalysisReport:
        started = time.perf_counter()
        try:
            return await asyncio.wait_for(self._analyze(prompt, started), self._timeout_s)
        except asyncio.TimeoutError:
            return _timeout_report(prompt, started, self._policy.fingerprint())

    async def _analyze(self, prompt: str, started: float) -> AnalysisReport:
        fingerprint = sha256_hex(prompt)
        # Layer 1
        with time_histogram(FIREWALL_PIPELINE_DURATION_SECONDS, stage="normalization"):
            normalized = normalization.normalize(prompt)
        # Layers 2 + 3 (independent, run sequentially — both are pure CPU)
        signal_list: list[Signal] = []
        with time_histogram(FIREWALL_PIPELINE_DURATION_SECONDS, stage="heuristics"):
            signal_list.extend(heuristics.evaluate(normalized))
        with time_histogram(FIREWALL_PIPELINE_DURATION_SECONDS, stage="patterns"):
            signal_list.extend(patterns.detect(normalized.text))
        # Layer 4: rules consume layers 1–3 output
        with time_histogram(FIREWALL_PIPELINE_DURATION_SECONDS, stage="rules"):
            signal_list.extend(self._rules.evaluate(normalized, signal_list))
        # Layer 5: LLM classifier (stub in Phase 4)
        llm_signals: list[Signal] = []
        llm_available = bool(getattr(self._llm, "available", False))
        if llm_available:
            with time_histogram(FIREWALL_PIPELINE_DURATION_SECONDS, stage="llm_classifier"):
                try:
                    llm_signals = await self._llm.classify(normalized)
                except Exception:  # noqa: BLE001 — the LLM is best-effort
                    llm_signals = []
                    llm_available = False
        signal_list.extend(llm_signals)

        # Layer 6: scoring
        with time_histogram(FIREWALL_PIPELINE_DURATION_SECONDS, stage="scoring"):
            score_result = score(signal_list, self._policy)

        # Pre-decision explainability (the policy engine will rebuild this
        # with the final reasoning summary; we attach matched rules /
        # patterns here so callers of /analyze still get the structure).
        explain = Explainability(
            matched_rules=tuple(sorted({s.rule_id for s in signal_list if s.rule_id})),
            triggered_patterns=tuple(
                sorted({s.pattern_id for s in signal_list if s.pattern_id})
            ),
            reasoning_summary=_pre_decision_summary(score_result.risk_score, signal_list),
            policy_hash=self._policy.fingerprint(),
            policy_references=self._policy.references,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)
        return AnalysisReport(
            prompt_fingerprint=fingerprint,
            prompt_length=len(prompt),
            normalized_length=normalized.normalized_length,
            risk_score=score_result.risk_score,
            risk_level=score_result.risk_level,
            classifications=score_result.classifications,
            signals=tuple(signal_list),
            explainability=explain,
            latency_ms=latency_ms,
            llm_classifier_available=llm_available,
            truncated=False,
        )


def _pre_decision_summary(score_value: float, signals: list[Signal]) -> str:
    return (
        f"score={score_value:.2f} signals={len(signals)} "
        f"rules={len({s.rule_id for s in signals if s.rule_id})} "
        f"patterns={len({s.pattern_id for s in signals if s.pattern_id})}"
    )


def _timeout_report(prompt: str, started: float, policy_hash: str) -> AnalysisReport:
    from firewall.risk.levels import RiskLevel
    latency_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisReport(
        prompt_fingerprint=sha256_hex(prompt),
        prompt_length=len(prompt),
        normalized_length=0,
        risk_score=0.0,
        risk_level=RiskLevel.SUSPICIOUS,
        classifications=(),
        signals=(),
        explainability=Explainability(
            matched_rules=(),
            triggered_patterns=(),
            reasoning_summary="firewall analysis timed out — defaulting to REVIEW",
            policy_hash=policy_hash,
            policy_references=(),
        ),
        latency_ms=latency_ms,
        llm_classifier_available=False,
        truncated=True,
    )
