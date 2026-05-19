"""Composite rule definitions.

A rule fires when *all* of its required pattern_ids are present in the
signal set AND *any* heuristic predicate it specifies is satisfied. This
captures the common case ("ignore-previous + role-tag in the same prompt
= confirmed injection, escalate severity") without inventing a DSL.

Each rule has a stable ``rule_id``, a :class:`Severity` band, a numeric
severity in [0,1] (what the emitted Signal carries), a weight, and
optional references (policy / framework citations rendered in the
explainability payload).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from firewall.analysis.normalization import NormalizationResult
from firewall.models.signals import Severity, Signal, ThreatCategory


HeuristicPredicate = Callable[[NormalizationResult], bool]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    category: ThreatCategory
    severity_band: Severity
    severity: float
    weight: float
    required_patterns: tuple[str, ...] = ()
    any_patterns: tuple[str, ...] = ()
    heuristic_predicates: tuple[HeuristicPredicate, ...] = ()
    references: tuple[str, ...] = ()
    sanitize: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.required_patterns and not self.any_patterns and not self.heuristic_predicates:
            raise ValueError(f"rule {self.rule_id!r} has no conditions")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError(f"rule {self.rule_id} severity out of range")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"rule {self.rule_id} weight out of range")


def _has_role_tag_density(r: NormalizationResult) -> bool:  # noqa: ARG001
    # Predicate inspects signals indirectly via pattern_ids; this slot is
    # for predicates that need normalization metadata (deep_encoding etc).
    return r.deep_encoding


RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        rule_id="r.injection.confirmed",
        category=ThreatCategory.PROMPT_INJECTION,
        severity_band=Severity.CRITICAL,
        severity=0.98,
        weight=1.0,
        required_patterns=("p.injection.ignore_previous",),
        any_patterns=("p.role.system_tag", "p.injection.system_reveal", "p.role.you_are_now"),
        references=("PLAN.md §1 (Security-for-AI)", "OWASP LLM01"),
        sanitize=True,
        description="confirmed prompt injection: explicit override + role/system reveal",
    ),
    RuleDefinition(
        rule_id="r.jailbreak.dan_with_role_play",
        category=ThreatCategory.JAILBREAK,
        severity_band=Severity.HIGH,
        severity=0.92,
        weight=0.95,
        any_patterns=("p.jailbreak.dan", "p.jailbreak.no_restrictions"),
        references=("OWASP LLM01",),
        sanitize=True,
        description="DAN-family or restriction-removal jailbreak",
    ),
    RuleDefinition(
        rule_id="r.role.system_tag_in_user_input",
        category=ThreatCategory.ROLE_MANIPULATION,
        severity_band=Severity.HIGH,
        severity=0.85,
        weight=0.90,
        required_patterns=("p.role.system_tag",),
        references=("OWASP LLM01",),
        sanitize=True,
        description="system role tag embedded in user prompt",
    ),
    RuleDefinition(
        rule_id="r.exfil.credentials",
        category=ThreatCategory.DATA_EXFILTRATION,
        severity_band=Severity.CRITICAL,
        severity=0.97,
        weight=1.0,
        any_patterns=("p.exfil.fetch_external", "p.exfil.print_secrets"),
        references=("OWASP LLM06",),
        sanitize=True,
        description="credential exfiltration directive",
    ),
    RuleDefinition(
        rule_id="r.tool.dangerous_shell",
        category=ThreatCategory.TOOL_ABUSE,
        severity_band=Severity.HIGH,
        severity=0.88,
        weight=0.90,
        any_patterns=("p.tool.shell_command", "p.tool.function_call_block"),
        references=("OWASP LLM07",),
        sanitize=True,
        description="tool-abuse / shell-injection pattern",
    ),
    RuleDefinition(
        rule_id="r.indirect.encoded_payload",
        category=ThreatCategory.INDIRECT_INJECTION,
        severity_band=Severity.HIGH,
        severity=0.82,
        weight=0.85,
        heuristic_predicates=(_has_role_tag_density,),
        any_patterns=("p.indirect.markdown_command", "p.indirect.hidden_html_comment"),
        references=("OWASP LLM01 (indirect)",),
        sanitize=True,
        description="indirect injection via encoded / hidden payload",
    ),
    RuleDefinition(
        rule_id="r.pii.high_value_secret",
        category=ThreatCategory.PII_DISCLOSURE,
        severity_band=Severity.HIGH,
        severity=0.90,
        weight=0.90,
        required_patterns=("p.pii.aws_key",),
        references=("CLAUDE.md invariant #12",),
        sanitize=True,
        description="AWS access key in prompt",
    ),
    RuleDefinition(
        rule_id="r.pii.contact_info",
        category=ThreatCategory.PII_DISCLOSURE,
        severity_band=Severity.MEDIUM,
        severity=0.55,
        weight=0.50,
        any_patterns=("p.pii.email", "p.pii.phone_e164"),
        references=("CLAUDE.md invariant #12",),
        sanitize=True,
        description="contact PII (email / phone) in prompt",
    ),
)


# Import-time sanity
_seen: set[str] = set()
for _r in RULES:
    assert _r.rule_id not in _seen, f"duplicate rule_id: {_r.rule_id}"
    _seen.add(_r.rule_id)
del _seen, _r


def rule_ids() -> tuple[str, ...]:
    return tuple(r.rule_id for r in RULES)
