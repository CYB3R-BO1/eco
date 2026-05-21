"""ReasoningAgent — the only LLM-driven agent in Phase 5.

Generates an investigation narrative summary by templating accumulated
deterministic findings into a versioned prompt, dogfooding the Phase 4
firewall analyze pipeline on the rendered prompt, then calling the
configured :class:`core.llm.client.LLMClient` (stub or OpenAI-compatible).
"""
from agents.reasoning.agent import ReasoningAgent
from agents.reasoning.prompts import PROMPT_TEMPLATES, ReasoningPrompt

__all__ = ["PROMPT_TEMPLATES", "ReasoningAgent", "ReasoningPrompt"]
