"""Agent runtime — Phase 5.

Each agent inherits :class:`agents.base.BaseAgent` and is invoked from a
LangGraph node. Agents are stateless; one instance per process per agent
class. The runtime constructs an :class:`agents.context.AgentExecutionContext`
per call.
"""
from agents.base import BaseAgent, compute_idempotency_key, inputs_fingerprint
from agents.context import AgentExecutionContext
from agents.enrichment.agent import EnrichmentAgent
from agents.firewall_analysis.agent import FirewallAnalysisAgent
from agents.ioc_correlation.agent import IOCCorrelationAgent
from agents.reasoning.agent import ReasoningAgent
from agents.result import AgentResult, AgentRunStatus

__all__ = [
    "AgentExecutionContext",
    "AgentResult",
    "AgentRunStatus",
    "BaseAgent",
    "EnrichmentAgent",
    "FirewallAnalysisAgent",
    "IOCCorrelationAgent",
    "ReasoningAgent",
    "compute_idempotency_key",
    "inputs_fingerprint",
]
