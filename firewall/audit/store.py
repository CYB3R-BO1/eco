"""FirewallAuditStore — writes one ``firewall_events`` row per call.

Insert-only. There's intentionally no update or delete method on the
store — invariant #12 forbids mutating audit records after the fact. If
something needs to be amended, a *new* row gets emitted with a metadata
link to the original.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from firewall.models.reports import Decision, ValidationReport
from firewall.models.signals import Signal
from firewall.models.prompt import PromptInput
from firewall.policy.actions import FirewallAction
from firewall.risk.levels import RiskLevel
from storage.postgres.models.firewall_event import FirewallEvent

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class FirewallAuditRecord:
    """Returned from :meth:`FirewallAuditStore.record_decision` so the
    rest of the pipeline can hang graph nodes off the firewall_event_id
    and surface it in the API response."""

    firewall_event_id: uuid.UUID
    investigation_id: uuid.UUID


class FirewallAuditStore:
    async def record_decision(
        self,
        session: AsyncSession,
        *,
        prompt_input: PromptInput,
        decision: Decision,
        investigation_id: uuid.UUID,
        evidence_refs: list[uuid.UUID],
        correlation_id: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> FirewallAuditRecord:
        row = FirewallEvent(
            id=uuid.uuid4(),
            correlation_id=correlation_id,
            investigation_id=investigation_id,
            prompt_sha256=decision.analysis.prompt_fingerprint,
            response_sha256=None,
            target_provider=prompt_input.target_model.provider,
            target_model=prompt_input.target_model.model,
            workflow_id=(
                prompt_input.workflow_context.workflow_id
                if prompt_input.workflow_context
                else None
            ),
            decision=decision.action,
            risk_level=decision.analysis.risk_level,
            risk_score=decision.analysis.risk_score,
            classifications=[c.value for c in decision.analysis.classifications],
            rule_ids=_unique_rule_ids(decision.analysis.signals),
            pattern_ids=_unique_pattern_ids(decision.analysis.signals),
            redaction_count=len(decision.redactions),
            policy_hash=decision.explainability.policy_hash,
            latency_ms=decision.analysis.latency_ms,
            evidence_refs=list(evidence_refs),
            is_output_validation=False,
            audit_metadata=dict(extra_metadata or {}),
            actor="firewall",
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.flush()
        log.info(
            "firewall.audit.recorded",
            firewall_event_id=str(row.id),
            decision=decision.action.value,
            risk_level=decision.analysis.risk_level.value,
            risk_score=decision.analysis.risk_score,
            classifications=row.classifications,
            prompt_sha256=row.prompt_sha256,
        )
        return FirewallAuditRecord(
            firewall_event_id=row.id,
            investigation_id=investigation_id,
        )

    async def record_validation(
        self,
        session: AsyncSession,
        *,
        report: ValidationReport,
        investigation_id: uuid.UUID,
        evidence_refs: list[uuid.UUID],
        prompt_fingerprint: str,
        target_provider: str,
        target_model: str,
        correlation_id: str | None = None,
    ) -> uuid.UUID:
        # An output validation maps onto the same audit shape as a
        # decision, with a synthetic FirewallAction so the timeline can
        # treat it uniformly. We invert the validator's outcomes:
        # PASS → ALLOW, SANITIZE → SANITIZE, BLOCK → BLOCK.
        outcome_action = {
            "PASS": FirewallAction.ALLOW,
            "SANITIZE": FirewallAction.SANITIZE,
            "BLOCK": FirewallAction.BLOCK,
        }[report.result.value]
        risk_level = (
            RiskLevel.MALICIOUS
            if report.result.value == "BLOCK"
            else RiskLevel.HIGH_RISK
            if report.result.value == "SANITIZE"
            else RiskLevel.SAFE
        )
        row = FirewallEvent(
            id=uuid.uuid4(),
            correlation_id=correlation_id,
            investigation_id=investigation_id,
            prompt_sha256=prompt_fingerprint,
            response_sha256=report.response_fingerprint,
            target_provider=target_provider,
            target_model=target_model,
            workflow_id=None,
            decision=outcome_action,
            risk_level=risk_level,
            risk_score=_max_severity(report.signals),
            classifications=[c.value for c in report.findings],
            rule_ids=_unique_rule_ids(list(report.signals)),
            pattern_ids=_unique_pattern_ids(list(report.signals)),
            redaction_count=len(report.redactions),
            policy_hash=report.policy_hash,
            latency_ms=report.latency_ms,
            evidence_refs=list(evidence_refs),
            is_output_validation=True,
            audit_metadata={"validation_result": report.result.value},
            actor="firewall",
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.flush()
        log.info(
            "firewall.audit.validation_recorded",
            firewall_event_id=str(row.id),
            result=report.result.value,
            response_sha256=row.response_sha256,
        )
        return row.id


def _unique_rule_ids(signals: list[Signal]) -> list[str]:
    return sorted({s.rule_id for s in signals if s.rule_id})


def _unique_pattern_ids(signals: list[Signal]) -> list[str]:
    return sorted({s.pattern_id for s in signals if s.pattern_id})


def _max_severity(signals: tuple[Signal, ...]) -> float:
    return max((s.severity for s in signals), default=0.0)
