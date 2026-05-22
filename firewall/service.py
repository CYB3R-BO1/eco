"""FirewallService — public facade.

Composes the analysis pipeline, policy engine, sanitizer, audit store,
graph correlator, and output validator into the three public coroutines
the API router calls:

* :meth:`analyze`         — read-only; runs pipeline + policy, returns ``AnalysisReport``
* :meth:`decide`          — stateful; persists investigation + audit + graph
* :meth:`validate_output` — analyzes a model response

All persistence (Investigation row, Evidence rows, FirewallEvent row,
state-machine transitions, graph mutations) happens inside this class so
the router stays a thin HTTP adapter.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from core.config.settings import FirewallSettings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.events.types import EventType
from core.observability.metrics import FIREWALL_DECISIONS_TOTAL, risk_bucket
from evidence.models import Evidence, Provenance
from evidence.provenance import ProvenanceLevel
from evidence.store import EvidenceStore
from firewall.audit.store import FirewallAuditStore
from firewall.correlation.correlator import FirewallGraphCorrelator
from firewall.models.prompt import PromptInput
from firewall.models.reports import (
    AnalysisReport,
    Decision,
    ValidationOutcome,
    ValidationReport,
)
from firewall.output_validation.validator import OutputValidator
from firewall.pipeline import PromptAnalysisPipeline
from firewall.policy.actions import FirewallAction
from firewall.policy.engine import PolicyEngine
from firewall.policy.policy import FirewallPolicy
from firewall.sanitization.redactor import apply as apply_sanitization
from graph.graph_service.service import GraphService
from investigation.lifecycle.manager import LifecycleManager
from investigation.lifecycle.states import InvestigationState
from storage.postgres.models.idempotency_key import IdempotencyKeyRow
from storage.postgres.models.investigation import Investigation

log = structlog.get_logger(__name__)


class PromptTooLargeError(ValueError):
    """Raised when the incoming prompt or response exceeds the configured byte cap."""

    def __init__(self, *, kind: str, length: int, limit: int) -> None:
        super().__init__(f"{kind} length {length} exceeds limit {limit}")
        self.kind = kind
        self.length = length
        self.limit = limit


class FirewallTimeoutError(RuntimeError):
    """Raised when the analysis pipeline times out and the caller chose to
    surface that as an error instead of a REQUIRE_REVIEW decision.

    Phase 4 always degrades to REQUIRE_REVIEW (per CLAUDE.md invariant
    #10), so this exception is only here as a hook for future callers that
    want stricter semantics.
    """


@dataclass(frozen=True)
class DecisionOutcome:
    decision: Decision
    investigation_id: uuid.UUID
    firewall_event_id: uuid.UUID


class FirewallService:
    def __init__(
        self,
        *,
        settings: FirewallSettings,
        database: Database,
        evidence_store: EvidenceStore,
        event_emitter: EventEmitter,
        lifecycle_manager: LifecycleManager,
        audit_store: FirewallAuditStore,
        graph_service: GraphService,
        graph_correlator: FirewallGraphCorrelator,
        pipeline: PromptAnalysisPipeline,
        policy_engine: PolicyEngine,
        output_validator: OutputValidator,
    ) -> None:
        self._settings = settings
        self._db = database
        self._evidence = evidence_store
        self._events = event_emitter
        self._lifecycle = lifecycle_manager
        self._audit = audit_store
        self._graph = graph_service
        self._correlator = graph_correlator
        self._pipeline = pipeline
        self._policy_engine = policy_engine
        self._output_validator = output_validator

    @property
    def policy(self) -> FirewallPolicy:
        return self._policy_engine.policy

    # ------------------------------------------------------------------
    # analyze (read-only)
    # ------------------------------------------------------------------
    async def analyze(self, prompt_input: PromptInput) -> AnalysisReport:
        self._enforce_prompt_limit(prompt_input.prompt)
        report = await self._pipeline.analyze(prompt_input.prompt)
        return report

    # ------------------------------------------------------------------
    # idempotency lookup (router uses this before /decision)
    # ------------------------------------------------------------------
    async def lookup_cached_decision(self, key: str) -> dict[str, Any] | None:
        async with self._db.session() as session:
            cached = await session.get(IdempotencyKeyRow, key)
        if cached is None:
            return None
        log.info("firewall.idempotent_replay", key=key)
        return cached.response

    # ------------------------------------------------------------------
    # decide (stateful)
    # ------------------------------------------------------------------
    async def decide(
        self,
        prompt_input: PromptInput,
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> DecisionOutcome:
        self._enforce_prompt_limit(prompt_input.prompt)

        report = await self._pipeline.analyze(prompt_input.prompt)
        action, explainability = self._policy_engine.decide(report)

        sanitized_prompt: str | None = None
        redactions: tuple[Any, ...] = ()
        if action is FirewallAction.SANITIZE:
            sanitized_prompt, redactions = apply_sanitization(
                _normalized_for_redaction(prompt_input.prompt, report),
                list(report.signals),
            )

        decision = Decision(
            analysis=report,
            action=action,
            sanitized_prompt=sanitized_prompt,
            redactions=tuple(redactions),
            explainability=explainability,
        )

        outcome = await self._persist_decision(
            prompt_input=prompt_input,
            decision=decision,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        FIREWALL_DECISIONS_TOTAL.labels(
            decision=action.value,
            risk_bucket=risk_bucket(report.risk_score),
        ).inc()
        return outcome

    # ------------------------------------------------------------------
    # validate_output
    # ------------------------------------------------------------------
    async def validate_output(
        self,
        *,
        response: str,
        prompt_fingerprint: str,
        investigation_id: uuid.UUID | None,
        target_provider: str | None = None,
        target_model: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationReport:
        if len(response.encode("utf-8")) > self._settings.max_output_bytes:
            raise PromptTooLargeError(
                kind="response",
                length=len(response.encode("utf-8")),
                limit=self._settings.max_output_bytes,
            )
        report = self._output_validator.validate(response)

        if investigation_id is not None:
            async with self._db.session() as session:
                # Record the validation Evidence (DERIVED_SOURCE, no raw text).
                ev = Evidence(
                    source="firewall_output_validator",
                    type="firewall_output_validation",
                    raw_data={
                        "response_sha256": report.response_fingerprint,
                        "prompt_sha256": prompt_fingerprint,
                        "result": report.result.value,
                        "findings": [c.value for c in report.findings],
                        "redaction_count": len(report.redactions),
                    },
                    normalized_data={},
                    confidence=max((s.severity for s in report.signals), default=0.0),
                    provenance=Provenance(
                        level=ProvenanceLevel.DERIVED_SOURCE,
                        source_reliability=0.95,
                        extraction_method="firewall_output_validation",
                        chain_of_custody=[],
                    ),
                    linked_entities=[],
                    investigation_id=investigation_id,
                )
                ev_id = await self._evidence.record(session, ev)
                await self._audit.record_validation(
                    session,
                    report=report,
                    investigation_id=investigation_id,
                    evidence_refs=[ev_id],
                    prompt_fingerprint=prompt_fingerprint,
                    target_provider=target_provider or "unknown",
                    target_model=target_model or "unknown",
                    correlation_id=correlation_id,
                )
                event_type = (
                    EventType.OUTPUT_BLOCKED
                    if report.result is ValidationOutcome.BLOCK
                    else EventType.OUTPUT_VALIDATED
                )
                await self._events.emit(
                    session,
                    event_type,
                    source="firewall",
                    investigation_id=investigation_id,
                    target=report.response_fingerprint,
                    evidence_refs=[ev_id],
                    metadata={
                        "result": report.result.value,
                        "findings": [c.value for c in report.findings],
                        "redaction_count": len(report.redactions),
                    },
                )
                await session.commit()
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _enforce_prompt_limit(self, prompt: str) -> None:
        length = len(prompt.encode("utf-8"))
        if length > self._settings.max_prompt_bytes:
            raise PromptTooLargeError(
                kind="prompt",
                length=length,
                limit=self._settings.max_prompt_bytes,
            )

    async def _persist_decision(
        self,
        *,
        prompt_input: PromptInput,
        decision: Decision,
        idempotency_key: str | None,
        correlation_id: str | None,
    ) -> DecisionOutcome:
        async with self._db.session() as session:
            # Investigation row
            investigation = Investigation(
                id=uuid.uuid4(),
                title=f"firewall:{decision.action.value}:{decision.analysis.prompt_fingerprint[:12]}",
                status=InvestigationState.CREATED,
                severity=_severity_for(decision.action),
                confidence_score=decision.analysis.risk_score,
            )
            session.add(investigation)
            await session.flush()

            # USER_SUPPLIED Evidence (fingerprint only — never raw text)
            user_ev = Evidence(
                source="firewall_ingress",
                type="firewall_prompt_fingerprint",
                raw_data={
                    "prompt_sha256": decision.analysis.prompt_fingerprint,
                    "length_bytes": decision.analysis.prompt_length,
                    "target_provider": prompt_input.target_model.provider,
                    "target_model": prompt_input.target_model.model,
                },
                normalized_data={},
                confidence=1.0,
                provenance=Provenance(
                    level=ProvenanceLevel.USER_SUPPLIED,
                    source_reliability=0.50,
                    extraction_method="firewall_ingress",
                    chain_of_custody=[],
                ),
                linked_entities=[],
                investigation_id=investigation.id,
            )
            user_ev_id = await self._evidence.record(session, user_ev)

            # DERIVED_SOURCE Evidence — the analysis report itself (no raw text)
            analysis_ev = Evidence(
                source="firewall_analysis",
                type="firewall_analysis_report",
                raw_data={
                    "prompt_sha256": decision.analysis.prompt_fingerprint,
                    "score": decision.analysis.risk_score,
                    "risk_level": decision.analysis.risk_level.value,
                    "classifications": [
                        c.value for c in decision.analysis.classifications
                    ],
                    "rule_ids": list(decision.explainability.matched_rules),
                    "pattern_ids": list(decision.explainability.triggered_patterns),
                    "policy_hash": decision.explainability.policy_hash,
                    "latency_ms": decision.analysis.latency_ms,
                    "llm_classifier_available": decision.analysis.llm_classifier_available,
                    "truncated": decision.analysis.truncated,
                },
                normalized_data={},
                confidence=decision.analysis.risk_score,
                provenance=Provenance(
                    level=ProvenanceLevel.DERIVED_SOURCE,
                    source_reliability=0.95,
                    extraction_method="firewall_pipeline",
                    chain_of_custody=[user_ev_id],
                ),
                linked_entities=[],
                investigation_id=investigation.id,
            )
            analysis_ev_id = await self._evidence.record(session, analysis_ev)

            evidence_refs = [user_ev_id, analysis_ev_id]

            # Head events
            await self._events.emit(
                session,
                EventType.PROMPT_RECEIVED,
                source="firewall",
                investigation_id=investigation.id,
                target=decision.analysis.prompt_fingerprint,
                evidence_refs=[user_ev_id],
                metadata={
                    "target_provider": prompt_input.target_model.provider,
                    "target_model": prompt_input.target_model.model,
                    "length_bytes": decision.analysis.prompt_length,
                },
            )
            await self._events.emit(
                session,
                EventType.PROMPT_ANALYZED,
                source="firewall",
                investigation_id=investigation.id,
                target=decision.analysis.prompt_fingerprint,
                evidence_refs=[analysis_ev_id],
                metadata={
                    "score": decision.analysis.risk_score,
                    "risk_level": decision.analysis.risk_level.value,
                    "decision": decision.action.value,
                    "policy_hash": decision.explainability.policy_hash,
                },
                confidence=decision.analysis.risk_score,
            )
            # Per-rule events (handy for SIEM ingestion)
            for rule_id in decision.explainability.matched_rules:
                await self._events.emit(
                    session,
                    EventType.FIREWALL_RULE_FIRED,
                    source="firewall",
                    investigation_id=investigation.id,
                    target=rule_id,
                    metadata={"rule_id": rule_id},
                )
            # Verdict event
            verdict_event = {
                FirewallAction.BLOCK: EventType.PROMPT_BLOCKED,
                FirewallAction.SANITIZE: EventType.PROMPT_SANITIZED,
                FirewallAction.REQUIRE_REVIEW: EventType.PROMPT_REQUIRES_REVIEW,
                FirewallAction.ALLOW: EventType.PROMPT_ANALYZED,
            }[decision.action]
            if decision.action is not FirewallAction.ALLOW:
                await self._events.emit(
                    session,
                    verdict_event,
                    source="firewall",
                    investigation_id=investigation.id,
                    target=decision.analysis.prompt_fingerprint,
                    evidence_refs=[analysis_ev_id],
                    metadata={
                        "redaction_count": len(decision.redactions),
                        "rule_ids": list(decision.explainability.matched_rules),
                    },
                    confidence=decision.analysis.risk_score,
                )

            # Audit row
            audit_record = await self._audit.record_decision(
                session,
                prompt_input=prompt_input,
                decision=decision,
                investigation_id=investigation.id,
                evidence_refs=evidence_refs,
                correlation_id=correlation_id,
            )

            # Drive the investigation through CREATED → ENRICHING → CORRELATING
            # so the eventual terminal state honors the Phase 3 FSM.
            await self._lifecycle.transition(
                session,
                investigation.id,
                InvestigationState.ENRICHING,
                reason="firewall analysis complete; correlating",
            )
            await self._lifecycle.transition(
                session,
                investigation.id,
                InvestigationState.CORRELATING,
                reason="firewall correlating graph",
            )
            await session.commit()

        # Graph correlation in a fresh session (the correlator emits its own events)
        async with self._db.session() as session:
            await self._correlator.correlate(
                session,
                investigation_id=audit_record.investigation_id,
                firewall_event_id=audit_record.firewall_event_id,
                prompt_input=prompt_input,
                decision=decision,
            )
            await session.commit()

        # Integrity gate + final transition
        report = await self._graph.integrity.check(audit_record.investigation_id)
        async with self._db.session() as session:
            if report.has_violations:
                await self._events.emit(
                    session,
                    EventType.INTEGRITY_VIOLATION_DETECTED,
                    source="firewall",
                    investigation_id=audit_record.investigation_id,
                    target=str(audit_record.investigation_id),
                    metadata=report.to_dict(),
                    confidence=0.0,
                )
                await self._lifecycle.transition(
                    session,
                    audit_record.investigation_id,
                    InvestigationState.REVIEW_REQUIRED,
                    reason="integrity violations detected post-firewall",
                )
            else:
                target_state = (
                    InvestigationState.REVIEW_REQUIRED
                    if decision.action is FirewallAction.REQUIRE_REVIEW
                    else InvestigationState.COMPLETED
                )
                await self._lifecycle.transition(
                    session,
                    audit_record.investigation_id,
                    target_state,
                    reason=f"firewall decision {decision.action.value}",
                )
            await session.commit()

        outcome = DecisionOutcome(
            decision=decision,
            investigation_id=audit_record.investigation_id,
            firewall_event_id=audit_record.firewall_event_id,
        )
        if idempotency_key:
            await self._store_idempotent(idempotency_key, outcome)
        return outcome

    async def _store_idempotent(self, key: str, outcome: DecisionOutcome) -> None:
        async with self._db.session() as session:
            session.add(
                IdempotencyKeyRow(
                    key=key,
                    response={
                        "investigation_id": str(outcome.investigation_id),
                        "firewall_event_id": str(outcome.firewall_event_id),
                        "decision": outcome.decision.action.value,
                        "risk_score": outcome.decision.analysis.risk_score,
                        "risk_level": outcome.decision.analysis.risk_level.value,
                        "classifications": [
                            c.value for c in outcome.decision.analysis.classifications
                        ],
                        "prompt_fingerprint": outcome.decision.analysis.prompt_fingerprint,
                        "matched_rules": list(outcome.decision.explainability.matched_rules),
                        "policy_hash": outcome.decision.explainability.policy_hash,
                    },
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()


def _normalized_for_redaction(prompt: str, report: AnalysisReport) -> str:
    """The sanitizer operates on normalized text — re-run normalization
    here rather than threading it through the report.

    Re-running is cheap (single NFKC pass + regex; no I/O) and keeps the
    report a pure data object instead of a closure over the original
    text.
    """
    from firewall.analysis.normalization import normalize
    return normalize(prompt).text if report else prompt


def _severity_for(action: FirewallAction) -> str:
    return {
        FirewallAction.ALLOW: "low",
        FirewallAction.SANITIZE: "medium",
        FirewallAction.REQUIRE_REVIEW: "medium",
        FirewallAction.BLOCK: "high",
    }[action]


def serialize_outcome(outcome: DecisionOutcome) -> dict[str, Any]:
    """Render a DecisionOutcome to the wire shape.

    Centralized here so the router and the idempotency cache write paths
    agree on the exact response keys.
    """
    d = outcome.decision
    return {
        "investigation_id": str(outcome.investigation_id),
        "firewall_event_id": str(outcome.firewall_event_id),
        "decision": d.action.value,
        "risk_score": d.analysis.risk_score,
        "risk_level": d.analysis.risk_level.value,
        "classifications": [c.value for c in d.analysis.classifications],
        "sanitized_prompt": d.sanitized_prompt,
        "redactions": [
            {
                "start": r.start,
                "end": r.end,
                "rule_id": r.rule_id,
                "replacement": r.replacement,
                "reason": r.reason,
            }
            for r in d.redactions
        ],
        "explainability": {
            "matched_rules": list(d.explainability.matched_rules),
            "triggered_patterns": list(d.explainability.triggered_patterns),
            "reasoning_summary": d.explainability.reasoning_summary,
            "policy_hash": d.explainability.policy_hash,
            "policy_references": list(d.explainability.policy_references),
        },
        "latency_ms": d.analysis.latency_ms,
        "llm_classifier_available": d.analysis.llm_classifier_available,
        "truncated": d.analysis.truncated,
        "prompt_fingerprint": d.analysis.prompt_fingerprint,
    }


__all__ = [
    "DecisionOutcome",
    "FirewallService",
    "FirewallTimeoutError",
    "PromptTooLargeError",
    "serialize_outcome",
]
