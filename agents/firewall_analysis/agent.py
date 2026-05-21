"""FirewallAnalysisAgent.

Wraps the **read-only** :meth:`FirewallService.analyze` path. This agent
is used in two places:

1. Inside the firewall workflow's ``firewall_decide_node`` — *not* this
   agent directly; that node calls ``FirewallService.decide`` (the
   stateful path). The firewall workflow's optional ``analyze_only`` node
   is what uses this agent.
2. As the prompt-safety gate inside :class:`ReasoningAgent` — see
   :mod:`agents.reasoning.agent`. There the analyze pipeline runs on the
   *rendered LLM prompt* before any LLM call; high-risk rendered prompts
   abort the call (PLAN.md §6 "do not let attacker input flow into LLM
   without firewall analysis").

Because :meth:`analyze` does not persist state, this agent never opens a
session. Its findings dict carries only fingerprints and scores — never
raw text — to keep the no-raw-text invariant intact in :attr:`AgentRunRow.findings_summary`.
"""
from __future__ import annotations

import time
from typing import Any

import structlog

from agents.base import BaseAgent
from agents.context import AgentExecutionContext
from agents.result import AgentResult, AgentRunStatus
from firewall.models.prompt import ModelTarget, PromptInput
from firewall.policy.actions import FirewallAction
from firewall.policy.engine import PolicyEngine
from firewall.service import FirewallService

log = structlog.get_logger(__name__)


class FirewallAnalysisAgent(BaseAgent):
    name = "firewall_analysis"
    timeout_seconds = 30
    max_retries = 0

    def __init__(
        self,
        *,
        firewall: FirewallService,
        policy_engine: PolicyEngine,
    ) -> None:
        self._firewall = firewall
        self._policy_engine = policy_engine

    async def _run(self, ctx: AgentExecutionContext) -> AgentResult:
        prompt = ctx.inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            return AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.FAILED,
                error="FirewallAnalysisAgent requires inputs.prompt: str",
            )

        target = ctx.inputs.get("target_model") or {}
        prompt_input = PromptInput(
            prompt=prompt,
            target_model=ModelTarget(
                provider=str(target.get("provider", "internal")),
                model=str(target.get("model", "reasoning")),
            ),
        )

        started = time.monotonic()
        report = await self._firewall.analyze(prompt_input)
        policy_action, _ = self._policy_engine.decide(report)

        findings: list[dict[str, Any]] = [
            {
                "prompt_sha256": report.prompt_fingerprint,
                "risk_score": report.risk_score,
                "risk_level": report.risk_level.value,
                "classifications": [c.value for c in report.classifications],
                "recommended_action": policy_action.value,
            }
        ]

        if policy_action is FirewallAction.BLOCK:
            status = AgentRunStatus.SUCCESS
            confidence = report.risk_score
        elif policy_action is FirewallAction.REQUIRE_REVIEW:
            status = AgentRunStatus.DEGRADED
            confidence = max(0.5, report.risk_score)
        elif policy_action is FirewallAction.SANITIZE:
            status = AgentRunStatus.DEGRADED
            confidence = 0.75
        else:  # ALLOW
            status = AgentRunStatus.SUCCESS
            confidence = 1.0 - report.risk_score

        return AgentResult(
            agent_run_id=ctx.agent_run_id,
            agent_name=self.name,
            status=status,
            evidence_refs=[],
            findings=findings,
            confidence=confidence,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={
                "policy_action": policy_action.value,
                "risk_level": report.risk_level.value,
            },
        )
