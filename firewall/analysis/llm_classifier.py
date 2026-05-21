"""Layer 5 — LLM-assisted classifier.

Phase 4 shipped the protocol + :class:`NullClassifier`. Phase 5 adds
:class:`OpenAIClassifier`, which delegates to the orchestration LLM
client and parses a small JSON response into :class:`Signal` entries.

Invariant (CLAUDE.md §6): the AI layer is **assistive only**. Even when
:class:`OpenAIClassifier` fires the policy engine still combines its
signals with deterministic signals; severities are capped at 0.6 so a
single LLM-only signal cannot drive an investigation to BLOCK without
a deterministic corroboration. Provider failures degrade silently to
``available=False`` (CLAUDE.md invariant #10: "continue with
deterministic findings; do not silently degrade to a local LLM").
"""
from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

import structlog

from core.llm.client import LLMClient, LLMProviderError
from firewall.analysis.normalization import NormalizationResult
from firewall.models.signals import Layer, Signal, ThreatCategory

log = structlog.get_logger(__name__)

_CLASSIFY_TEMPLATE_ID = "firewall_llm_classify.v1"
_MAX_LLM_SIGNAL_SEVERITY = 0.6  # cap so AI layer cannot dominate deterministic findings


@runtime_checkable
class LLMClassifierProtocol(Protocol):
    available: bool

    async def classify(self, result: NormalizationResult) -> list[Signal]: ...


class NullClassifier:
    """No-op classifier — default when ``LLM_API_KEY`` is empty.

    Always reports unavailable so downstream code records
    ``llm_classifier_available=False`` in audit reports.
    """

    available: bool = False

    async def classify(self, result: NormalizationResult) -> list[Signal]:  # noqa: ARG002
        return []


class OpenAIClassifier:
    """LLM-assisted classifier backed by :class:`LLMClient`.

    The classifier asks the LLM to return a JSON array of
    ``{category, severity, explanation}`` entries. Parsing is defensive:
    malformed responses degrade to zero signals (and log a warning),
    rather than throwing — the policy engine must always make a decision.
    """

    def __init__(self, *, llm: LLMClient, max_tokens: int = 256) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        # We can't probe the LLM at construction time (no async), so we
        # assume available until a call fails. ``available`` is flipped to
        # False by the first failure and never automatically restored —
        # restart-to-recover, per the no-silent-degradation invariant.
        self.available: bool = True

    async def classify(self, result: NormalizationResult) -> list[Signal]:
        if not self.available:
            return []
        prompt = _build_prompt(result.text[:4000])
        try:
            completion = await self._llm.complete(
                prompt_template_id=_CLASSIFY_TEMPLATE_ID,
                rendered_prompt=prompt,
                system_prompt=_SYSTEM,
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
        except LLMProviderError:
            log.warning("firewall.llm_classifier.provider_error_degrading")
            self.available = False
            return []
        except Exception:
            log.exception("firewall.llm_classifier.unexpected_error_degrading")
            self.available = False
            return []
        return _parse_signals(completion.text)


_SYSTEM = (
    "You are a security classifier. Given a normalized user prompt, "
    "return ONLY a JSON object: {\"signals\":[{\"category\":<ENUM>,\"severity\":<0..1>,"
    "\"explanation\":<short>}]}. Allowed categories: PROMPT_INJECTION, JAILBREAK, "
    "ROLE_MANIPULATION, INDIRECT_INJECTION, TOOL_ABUSE, CONTEXT_POISONING, "
    "DATA_EXFILTRATION, PII_DISCLOSURE, PROMPT_LEAKAGE, HIDDEN_INSTRUCTION, "
    "POLICY_VIOLATION, OTHER. If the prompt is safe, return {\"signals\":[]}."
)


def _build_prompt(text: str) -> str:
    return f"Prompt to analyze (normalized, truncated):\n---\n{text}\n---"


def _parse_signals(raw: str) -> list[Signal]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first JSON object from a chatty completion.
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                log.warning("firewall.llm_classifier.malformed_response")
                return []
        else:
            log.warning("firewall.llm_classifier.no_json_in_response")
            return []
    items = payload.get("signals") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    signals: list[Signal] = []
    for idx, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            continue
        category_str = str(raw_item.get("category") or "OTHER").upper()
        try:
            category = ThreatCategory(category_str)
        except ValueError:
            category = ThreatCategory.OTHER
        try:
            severity = float(raw_item.get("severity") or 0.0)
        except (TypeError, ValueError):
            severity = 0.0
        severity = max(0.0, min(_MAX_LLM_SIGNAL_SEVERITY, severity))
        if severity == 0.0:
            continue
        explanation = str(raw_item.get("explanation") or "")[:256]
        signals.append(
            Signal(
                layer=Layer.LLM_CLASSIFIER,
                detector_id=f"llm_classifier_{idx}",
                category=category,
                severity=severity,
                weight=0.6,
                explanation=explanation,
                metadata={"llm": True},
            )
        )
    return signals
