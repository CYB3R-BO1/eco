"""AI Firewall router — three endpoints.

All three are POST. ``/analyze`` is read-only (idempotent, no state
change). ``/decision`` mutates: it creates an Investigation, writes the
audit row, materializes the graph correlation, and emits events.
``/validate-output`` is the response-side counterpart of /analyze plus
an optional persistence path when ``investigation_id`` is supplied.
"""
from __future__ import annotations

from fastapi import APIRouter, Header

from apps.api.dependencies import FirewallServiceDep
from firewall.models.prompt import ModelTarget, PromptInput, WorkflowContext
from firewall.service import serialize_outcome
from schemas.api.firewall import (
    AnalysisResponse,
    AnalyzeRequest,
    DecisionRequest,
    DecisionResponse,
    ExplainabilityDTO,
    RedactionDTO,
    SignalDTO,
    ValidateOutputRequest,
    ValidateOutputResponse,
)

router = APIRouter(prefix="/firewall", tags=["firewall"])


def _to_prompt_input(body: AnalyzeRequest) -> PromptInput:
    return PromptInput(
        prompt=body.prompt,
        target_model=ModelTarget(
            provider=body.target_model.provider,
            model=body.target_model.model,
        ),
        workflow_context=(
            WorkflowContext(
                workflow_id=body.workflow_context.workflow_id,
                route=body.workflow_context.route,
            )
            if body.workflow_context
            else None
        ),
    )


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Analyze a prompt without persisting or correlating.",
)
async def analyze(body: AnalyzeRequest, fw: FirewallServiceDep) -> AnalysisResponse:
    report = await fw.analyze(_to_prompt_input(body))
    return AnalysisResponse(
        prompt_fingerprint=report.prompt_fingerprint,
        prompt_length=report.prompt_length,
        normalized_length=report.normalized_length,
        risk_score=report.risk_score,
        risk_level=report.risk_level.value,
        classifications=[c.value for c in report.classifications],
        signals=[_signal_dto(s) for s in report.signals],
        explainability=_explainability_dto(report.explainability),
        latency_ms=report.latency_ms,
        llm_classifier_available=report.llm_classifier_available,
        truncated=report.truncated,
    )


@router.post(
    "/decision",
    response_model=DecisionResponse,
    summary="Run firewall, persist the audit + investigation, and return the decision.",
)
async def decide(
    body: DecisionRequest,
    fw: FirewallServiceDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> DecisionResponse:
    if idempotency_key:
        cached = await fw.lookup_cached_decision(idempotency_key)
        if cached is not None:
            return _decision_from_cached(cached)

    outcome = await fw.decide(
        _to_prompt_input(body),
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    payload = serialize_outcome(outcome)
    return _decision_from_serialized(payload)


@router.post(
    "/validate-output",
    response_model=ValidateOutputResponse,
    summary="Validate a model response for leakage / hidden instructions / PII.",
)
async def validate_output(
    body: ValidateOutputRequest,
    fw: FirewallServiceDep,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> ValidateOutputResponse:
    report = await fw.validate_output(
        response=body.response,
        prompt_fingerprint=body.prompt_fingerprint,
        investigation_id=body.investigation_id,
        target_provider=body.target_model.provider if body.target_model else None,
        target_model=body.target_model.model if body.target_model else None,
        correlation_id=correlation_id,
    )
    return ValidateOutputResponse(
        response_fingerprint=report.response_fingerprint,
        result=report.result.value,
        sanitized_response=report.sanitized_response,
        findings=[c.value for c in report.findings],
        redactions=[
            RedactionDTO(
                start=r.start,
                end=r.end,
                rule_id=r.rule_id,
                replacement=r.replacement,
                reason=r.reason,
            )
            for r in report.redactions
        ],
        reasoning_summary=report.reasoning_summary,
        policy_hash=report.policy_hash,
        latency_ms=report.latency_ms,
    )


# ---------------------------------------------------------------------------
# DTO helpers
# ---------------------------------------------------------------------------

def _signal_dto(s) -> SignalDTO:
    return SignalDTO(
        layer=s.layer.value,
        detector_id=s.detector_id,
        category=s.category.value,
        severity=s.severity,
        weight=s.weight,
        evidence_span=s.evidence_span,
        explanation=s.explanation,
        rule_id=s.rule_id,
        pattern_id=s.pattern_id,
        metadata=dict(s.metadata),
    )


def _explainability_dto(e) -> ExplainabilityDTO:
    return ExplainabilityDTO(
        matched_rules=list(e.matched_rules),
        triggered_patterns=list(e.triggered_patterns),
        reasoning_summary=e.reasoning_summary,
        policy_hash=e.policy_hash,
        policy_references=list(e.policy_references),
    )


def _decision_from_serialized(payload: dict) -> DecisionResponse:
    return DecisionResponse(
        investigation_id=payload["investigation_id"],
        firewall_event_id=payload["firewall_event_id"],
        decision=payload["decision"],
        risk_score=payload["risk_score"],
        risk_level=payload["risk_level"],
        classifications=payload["classifications"],
        prompt_fingerprint=payload["prompt_fingerprint"],
        sanitized_prompt=payload.get("sanitized_prompt"),
        redactions=[RedactionDTO(**r) for r in payload.get("redactions", [])],
        explainability=ExplainabilityDTO(**payload["explainability"]),
        latency_ms=payload["latency_ms"],
        llm_classifier_available=payload["llm_classifier_available"],
        truncated=payload["truncated"],
    )


def _decision_from_cached(payload: dict) -> DecisionResponse:
    """The cached row stores a slim shape (no signals / redactions). Wrap
    it back into the full response by filling defaults for the omitted
    fields. We keep the cached shape slim deliberately — the audit
    trail in Postgres / Neo4j is authoritative; the cached body just
    needs to give the caller the same decision they would've seen."""
    return DecisionResponse(
        investigation_id=payload["investigation_id"],
        firewall_event_id=payload["firewall_event_id"],
        decision=payload["decision"],
        risk_score=payload["risk_score"],
        risk_level=payload["risk_level"],
        classifications=payload.get("classifications", []),
        prompt_fingerprint=payload.get("prompt_fingerprint", ""),
        sanitized_prompt=None,
        redactions=[],
        explainability=ExplainabilityDTO(
            matched_rules=payload.get("matched_rules", []),
            triggered_patterns=[],
            reasoning_summary="replay of cached decision",
            policy_hash=payload.get("policy_hash", ""),
            policy_references=[],
        ),
        latency_ms=0,
        llm_classifier_available=False,
        truncated=False,
    )
