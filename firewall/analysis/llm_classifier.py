"""Layer 5 — LLM-assisted classifier (Phase 4: stub).

Phase 4 ships the protocol so the rest of the pipeline can be wired and
tested end-to-end. The real provider integration lands in Phase 5; we
keep the slot here so the pipeline shape is final.

The :class:`NullClassifier` returns an empty signal list and reports
``available=False`` — the policy engine knows to treat the score as
deterministic-only in that case (CLAUDE.md invariant #10).

A future real implementation should:

* respect ``detection_timeout_ms`` from settings (wrap in ``asyncio.wait_for``),
* surface circuit-breaker state via ``available``,
* emit signals citing the LLM's own reasoning as ``explanation`` — but
  the signal severity must still be ≤ pattern-layer ceilings so the AI
  layer cannot dominate deterministic findings.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from firewall.analysis.normalization import NormalizationResult
from firewall.models.signals import Signal


@runtime_checkable
class LLMClassifierProtocol(Protocol):
    available: bool

    async def classify(self, result: NormalizationResult) -> list[Signal]: ...


class NullClassifier:
    """No-op classifier — Phase 4 default.

    Always reports unavailable so downstream code records
    ``llm_classifier_available=False`` in audit reports.
    """

    available: bool = False

    async def classify(self, result: NormalizationResult) -> list[Signal]:  # noqa: ARG002
        return []
