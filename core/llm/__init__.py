"""LLM client surface.

Phase 5 exposes a single ``LLMClient`` Protocol with two implementations:
:class:`StubLLM` (deterministic, no network) and :class:`OpenAIClient` (real,
OpenAI-compatible HTTP). ``build_llm_client(settings)`` picks the right one
based on ``LLM_API_KEY`` — tests always get the stub.
"""
from __future__ import annotations

from core.llm.budget import InvestigationTokenBudget, TokenBudgetExceeded
from core.llm.client import (
    LLMClient,
    LLMCompletion,
    LLMProviderError,
    OpenAIClient,
    StubLLM,
    build_llm_client,
)
from core.llm.tokens import AITokenUsage, TokenMeter, estimate_tokens

__all__ = [
    "AITokenUsage",
    "InvestigationTokenBudget",
    "LLMClient",
    "LLMCompletion",
    "LLMProviderError",
    "OpenAIClient",
    "StubLLM",
    "TokenBudgetExceeded",
    "TokenMeter",
    "build_llm_client",
    "estimate_tokens",
]
