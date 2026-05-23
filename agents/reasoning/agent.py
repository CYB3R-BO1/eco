"""ReasoningAgent — LLM-driven investigation summarizer.

Flow:

1. Pull recent findings from ``ctx.inputs['findings']`` (workflow state
   accumulator) and accumulated memory entries via ``ctx.memory.recall``.
2. Render the ``investigation_summary.v1`` prompt template with the
   findings block.
3. Run the Phase 4 firewall ``analyze`` on the *rendered* prompt. If the
   firewall returns BLOCK or REQUIRE_REVIEW (i.e. evidence contains
   injected text that would attack the downstream LLM), abort the call,
   emit ``REASONING_BLOCKED_BY_FIREWALL`` and return ``AI_UNAVAILABLE``.
4. Reserve estimated tokens on the investigation budget. On failure,
   emit ``AI_UNAVAILABLE`` and skip the LLM call.
5. Call the LLM client. On any exception, release the reservation, emit
   ``AI_UNAVAILABLE``, return ``AI_UNAVAILABLE``.
6. Commit the actual token usage to the budget, persist the completion
   fingerprint to memory + evidence (DERIVED_SOURCE), return ``SUCCESS``.

Notes:
- Completion text lives in an Evidence row (AI_GENERATED provenance) —
  not in any orchestration table. Audit columns store only fingerprints.
- The summary is *assistive only* (CLAUDE.md invariant #5). Deterministic
  findings stay authoritative.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from agents.base import BaseAgent
from agents.context import AgentExecutionContext
from agents.reasoning.prompts import PROMPT_TEMPLATES, ReasoningPrompt
from agents.result import AgentResult, AgentRunStatus
from core.events.types import EventType
from core.llm.client import LLMClient, LLMProviderError
from core.llm.budget import TokenBudgetExceeded
from core.llm.tokens import AITokenUsage, estimate_tokens
from evidence.models import Evidence, Provenance
from evidence.provenance import ProvenanceLevel
from evidence.store import EvidenceStore
from firewall.models.prompt import ModelTarget, PromptInput
from firewall.policy.actions import FirewallAction
from firewall.policy.engine import PolicyEngine
from firewall.service import FirewallService
from orchestration.memory.entry import MemoryEntry

log = structlog.get_logger(__name__)

_DEFAULT_TEMPLATE_ID = "investigation_summary.v1"
_MAX_FINDINGS_RENDERED = 15
_MAX_FINDING_CHARS = 400


class ReasoningAgent(BaseAgent):
    name = "reasoning"
    timeout_seconds = 60
    max_retries = 0

    def __init__(
        self,
        *,
        llm: LLMClient,
        firewall: FirewallService,
        policy_engine: PolicyEngine,
        evidence_store: EvidenceStore,
        prompt_safety_enabled: bool = True,
        max_completion_tokens: int = 1024,
    ) -> None:
        self._llm = llm
        self._firewall = firewall
        self._policy_engine = policy_engine
        self._evidence_store = evidence_store
        self._prompt_safety_enabled = prompt_safety_enabled
        self._max_completion_tokens = max_completion_tokens

    async def _run(self, ctx: AgentExecutionContext) -> AgentResult:
        """Orchestrate the reasoning agent's three phases.

        Phase 7 WP5 split the original 160-line implementation into
        three focused coroutines — ``_check_firewall``,
        ``_call_llm_with_budget``, and ``_persist_completion`` — so the
        control flow reads top-to-bottom in this method.
        """
        if ctx.investigation_id is None:
            return AgentResult(
                agent_run_id=ctx.agent_run_id,
                agent_name=self.name,
                status=AgentRunStatus.FAILED,
                error="ReasoningAgent requires an investigation_id",
            )

        started = time.monotonic()
        template = PROMPT_TEMPLATES[_DEFAULT_TEMPLATE_ID]
        rendered = await self._render(ctx, template)

        if self._prompt_safety_enabled:
            blocked_result = await self._check_firewall(ctx, rendered, started)
            if blocked_result is not None:
                return blocked_result

        completion_or_failure = await self._call_llm_with_budget(
            ctx, template, rendered, started
        )
        if isinstance(completion_or_failure, AgentResult):
            return completion_or_failure
        completion = completion_or_failure

        return await self._persist_completion(
            ctx, template, rendered, completion, started
        )

    async def _render(
        self,
        ctx: AgentExecutionContext,
        template: ReasoningPrompt,
    ) -> str:
        """Pull memory + findings and render the prompt template."""
        findings = list(ctx.inputs.get("findings") or [])
        memory_entries: list[MemoryEntry] = []
        if ctx.memory is not None:
            try:
                memory_entries = await ctx.memory.list()
            except Exception:
                log.exception("agent.reasoning.memory_list_failed")
        return self._render_prompt(
            template,
            investigation_id=ctx.investigation_id,
            findings=findings,
            memory_entries=memory_entries,
        )

    async def _check_firewall(
        self,
        ctx: AgentExecutionContext,
        rendered: str,
        started: float,
    ) -> AgentResult | None:
        """Run the firewall over the rendered prompt; emit + bail on block.

        Returns ``None`` when the prompt passes (caller continues); an
        ``AgentResult`` with status ``AI_UNAVAILABLE`` when the firewall
        flagged BLOCK or REQUIRE_REVIEW.
        """
        blocked = await self._firewall_blocks(rendered)
        if blocked is None:
            return None
        async with ctx.database.session() as session:
            await ctx.event_emitter.emit(
                session,
                EventType.REASONING_BLOCKED_BY_FIREWALL,
                source=f"agent:{self.name}",
                investigation_id=ctx.investigation_id,
                target=str(ctx.agent_run_id),
                metadata={"firewall_action": blocked},
                actor=f"agent:{self.name}",
                confidence=0.0,
            )
            await session.commit()
        return AgentResult(
            agent_run_id=ctx.agent_run_id,
            agent_name=self.name,
            status=AgentRunStatus.AI_UNAVAILABLE,
            error=f"rendered prompt blocked by firewall: {blocked}",
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"firewall_action": blocked},
        )

    async def _call_llm_with_budget(
        self,
        ctx: AgentExecutionContext,
        template: ReasoningPrompt,
        rendered: str,
        started: float,
    ) -> Any:
        """Reserve tokens, call the LLM, commit/release on result.

        Returns the completion object on success, an ``AgentResult``
        with ``AI_UNAVAILABLE`` on any failure (budget exceeded,
        provider error, unknown exception).
        """
        estimated_in = estimate_tokens(template.system) + estimate_tokens(rendered)
        reservation = estimated_in + self._max_completion_tokens
        if ctx.token_budget is not None:
            try:
                await ctx.token_budget.reserve(ctx.investigation_id, reservation)
            except TokenBudgetExceeded as exc:
                return await self._emit_ai_unavailable(
                    ctx,
                    started,
                    reason=(
                        f"token budget exceeded: "
                        f"requested={exc.requested} remaining={exc.remaining}"
                    ),
                )

        try:
            completion = await self._llm.complete(
                prompt_template_id=template.template_id,
                rendered_prompt=rendered,
                system_prompt=template.system,
                max_tokens=self._max_completion_tokens,
                temperature=0.0,
            )
        except LLMProviderError as exc:
            if ctx.token_budget is not None:
                await ctx.token_budget.release(ctx.investigation_id, reservation)
            return await self._emit_ai_unavailable(
                ctx, started, reason=f"llm provider error: {exc}"
            )
        except Exception as exc:
            if ctx.token_budget is not None:
                await ctx.token_budget.release(ctx.investigation_id, reservation)
            log.exception("agent.reasoning.llm_call_failed")
            return await self._emit_ai_unavailable(
                ctx, started, reason=f"{type(exc).__name__}: {exc}"
            )

        # Reconcile reservation with actual usage. The reservation was an
        # upper bound; commit the truthy usage so the budget tracks reality.
        if ctx.token_budget is not None:
            try:
                await ctx.token_budget.commit(
                    ctx.investigation_id,
                    reserved=reservation,
                    actual=completion.usage.total,
                )
            except Exception:
                log.exception("agent.reasoning.budget_commit_failed")
        return completion

    async def _persist_completion(
        self,
        ctx: AgentExecutionContext,
        template: ReasoningPrompt,
        rendered: str,
        completion: Any,
        started: float,
    ) -> AgentResult:
        """Write the AI_GENERATED Evidence row + memory entry + summary."""
        evidence_refs: list[uuid.UUID] = []
        async with ctx.database.session() as session:
            ev = Evidence(
                source="reasoning_agent",
                type="reasoning_summary",
                raw_data={
                    "prompt_template_id": template.template_id,
                    "prompt_sha256": _sha256(rendered),
                    "completion_sha256": _sha256(completion.text),
                    "completion_length": len(completion.text),
                    "provider": completion.provider,
                    "model": completion.model,
                    "finish_reason": completion.finish_reason,
                    "tokens_input": completion.usage.input,
                    "tokens_output": completion.usage.output,
                },
                normalized_data={"summary": completion.text},
                confidence=0.6,
                provenance=Provenance(
                    level=ProvenanceLevel.AI_GENERATED,
                    source_reliability=0.6,
                    extraction_method="reasoning_llm",
                    chain_of_custody=[],
                ),
                linked_entities=[],
                investigation_id=ctx.investigation_id,
            )
            ev_id = await self._evidence_store.record(session, ev)
            await session.commit()
            evidence_refs.append(ev_id)

        if ctx.memory is not None:
            try:
                memory_entry = MemoryEntry.new(
                    investigation_id=ctx.investigation_id,
                    agent_name=self.name,
                    summary=completion.text,
                    payload={"evidence_id": str(ev_id)},
                )
                await ctx.memory.append(memory_entry)
            except Exception:
                log.exception("agent.reasoning.memory_append_failed")

        return AgentResult(
            agent_run_id=ctx.agent_run_id,
            agent_name=self.name,
            status=AgentRunStatus.SUCCESS,
            evidence_refs=evidence_refs,
            findings=[
                {
                    "prompt_template_id": template.template_id,
                    "completion_sha256": _sha256(completion.text),
                    "tokens_input": completion.usage.input,
                    "tokens_output": completion.usage.output,
                    "provider": completion.provider,
                    "model": completion.model,
                }
            ],
            confidence=0.6,
            ai_tokens=completion.usage,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"provider": completion.provider},
        )

    async def _firewall_blocks(self, rendered_prompt: str) -> str | None:
        """Returns the action name if BLOCK/REQUIRE_REVIEW; None if safe."""
        try:
            report = await self._firewall.analyze(
                PromptInput(
                    prompt=rendered_prompt,
                    target_model=ModelTarget(provider="internal", model="reasoning"),
                )
            )
        except Exception:
            log.exception("agent.reasoning.firewall_analyze_failed")
            return None
        action, _ = self._policy_engine.decide(report)
        if action in (FirewallAction.BLOCK, FirewallAction.REQUIRE_REVIEW):
            return action.value
        return None

    async def _emit_ai_unavailable(
        self,
        ctx: AgentExecutionContext,
        started: float,
        *,
        reason: str,
    ) -> AgentResult:
        async with ctx.database.session() as session:
            await ctx.event_emitter.emit(
                session,
                EventType.AI_UNAVAILABLE,
                source=f"agent:{self.name}",
                investigation_id=ctx.investigation_id,
                target=str(ctx.agent_run_id),
                metadata={"reason": reason[:512]},
                actor=f"agent:{self.name}",
                confidence=0.0,
            )
            await session.commit()
        return AgentResult(
            agent_run_id=ctx.agent_run_id,
            agent_name=self.name,
            status=AgentRunStatus.AI_UNAVAILABLE,
            error=reason[:512],
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    @staticmethod
    def _render_prompt(
        template: ReasoningPrompt,
        *,
        investigation_id: uuid.UUID,
        findings: list[dict[str, Any]],
        memory_entries: list[MemoryEntry],
    ) -> str:
        # Build a deterministic, bounded findings block.
        rendered_findings: list[str] = []
        for idx, finding in enumerate(findings[:_MAX_FINDINGS_RENDERED]):
            text = _safe_str(finding)[:_MAX_FINDING_CHARS]
            rendered_findings.append(f"[{idx}] {text}")
        if memory_entries:
            rendered_findings.append("---memory---")
            for idx, entry in enumerate(memory_entries[:5]):
                rendered_findings.append(
                    f"[m{idx}/{entry.agent_name}] "
                    f"{entry.summary[:_MAX_FINDING_CHARS]}"
                )
        findings_block = "\n".join(rendered_findings) or "(no findings)"
        return template.render(
            {
                "investigation_id": str(investigation_id),
                "finding_count": str(len(findings)),
                "findings_block": findings_block,
            }
        )


def _safe_str(obj: Any) -> str:
    try:
        if isinstance(obj, dict):
            return ", ".join(f"{k}={obj[k]}" for k in sorted(obj.keys()))
        return str(obj)
    except Exception:
        return "<unrenderable>"


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
