"""Versioned reasoning prompts.

Every prompt has a stable :class:`prompt_template_id` ending in ``.vN`` so
the audit row (``agent_runs.findings_summary.prompt_template_id``) lets
auditors trace exactly which template a completion came from. User data
is **never** interpolated via f-strings or ``%`` — only via the
explicit ``variables`` dict on :class:`ReasoningPrompt.render`. This is
the seam where the Phase 4 firewall analyzes the rendered prompt
(see :meth:`ReasoningAgent._run`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReasoningPrompt:
    template_id: str
    system: str
    user_template: str
    expected_variables: tuple[str, ...]

    def render(self, variables: dict[str, str]) -> str:
        missing = set(self.expected_variables) - set(variables.keys())
        if missing:
            raise ValueError(
                f"reasoning prompt {self.template_id} missing variables: {sorted(missing)}"
            )
        return self.user_template.format(**variables)


_INVESTIGATION_SUMMARY_V1 = ReasoningPrompt(
    template_id="investigation_summary.v1",
    system=(
        "You are a security investigation summarizer. Read the structured "
        "deterministic findings below and produce a short narrative (3-6 "
        "sentences) describing the threat, the strongest evidence, and the "
        "recommended analyst action. Cite findings by their index. Never "
        "speculate beyond what the findings state."
    ),
    user_template=(
        "Investigation ID: {investigation_id}\n"
        "Findings count: {finding_count}\n"
        "Findings (truncated):\n{findings_block}\n\n"
        "Produce a summary."
    ),
    expected_variables=("investigation_id", "finding_count", "findings_block"),
)


PROMPT_TEMPLATES: dict[str, ReasoningPrompt] = {
    _INVESTIGATION_SUMMARY_V1.template_id: _INVESTIGATION_SUMMARY_V1,
}
