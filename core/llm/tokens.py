"""Token accounting helpers.

Phase 5 does **not** bundle a real tokenizer — adding ``tiktoken`` would pull
a multi-MB C extension for a budget-enforcement use case where 10% accuracy
is fine. ``estimate_tokens`` uses the well-known "~4 chars per token" rule
of thumb. Callers that need exact counts post-call should read the LLM
provider's returned ``usage`` block instead.
"""
from __future__ import annotations

from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ceil(len/4). Good enough for budget checks."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


@dataclass(frozen=True)
class AITokenUsage:
    input: int = 0
    output: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output

    def add(self, other: AITokenUsage) -> AITokenUsage:
        return AITokenUsage(input=self.input + other.input, output=self.output + other.output)

    def to_dict(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output, "total": self.total}


class TokenMeter:
    """Mutable accumulator. One instance per agent run."""

    __slots__ = ("_input", "_output")

    def __init__(self) -> None:
        self._input = 0
        self._output = 0

    def record(self, *, input_tokens: int, output_tokens: int) -> None:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        self._input += input_tokens
        self._output += output_tokens

    def snapshot(self) -> AITokenUsage:
        return AITokenUsage(input=self._input, output=self._output)
