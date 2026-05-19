"""Signal — the unit of evidence produced by every analysis layer.

Each detector (heuristic check, regex pattern, composite rule, LLM
classifier) emits zero or more Signals. A Signal carries:

* ``layer``        — which pipeline stage produced it
* ``detector_id``  — stable identifier for that specific check
* ``category``     — which :class:`ThreatCategory` it implicates
* ``severity``     — strength of the individual signal in [0, 1]
* ``weight``       — how much that signal contributes to the category score
                     in [0, 1]; lets us tune the catalog without changing severities
* ``evidence_span`` — (start, end) byte offsets into the normalized prompt,
                      or ``None`` for whole-prompt signals
* ``explanation``  — short human-readable note (no raw prompt slice; the
                     offsets identify the span)
* ``rule_id`` / ``pattern_id`` — provenance back to the catalog entries

Severities must stay in [0, 1]; the scorer assumes that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Layer(str, Enum):
    NORMALIZATION = "normalization"
    HEURISTIC = "heuristic"
    PATTERN = "pattern"
    RULE = "rule"
    LLM_CLASSIFIER = "llm_classifier"


class ThreatCategory(str, Enum):
    PROMPT_INJECTION = "PROMPT_INJECTION"
    JAILBREAK = "JAILBREAK"
    ROLE_MANIPULATION = "ROLE_MANIPULATION"
    INDIRECT_INJECTION = "INDIRECT_INJECTION"
    TOOL_ABUSE = "TOOL_ABUSE"
    CONTEXT_POISONING = "CONTEXT_POISONING"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    PII_DISCLOSURE = "PII_DISCLOSURE"
    PROMPT_LEAKAGE = "PROMPT_LEAKAGE"
    HIDDEN_INSTRUCTION = "HIDDEN_INSTRUCTION"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    OTHER = "OTHER"


class Severity(str, Enum):
    """Catalog-level severity bands.

    Distinct from the numeric ``Signal.severity`` field: this enum is
    attached to *rules*, the numeric is attached to *fires*. A rule with
    ``Severity.CRITICAL`` short-circuits the policy engine to BLOCK
    regardless of aggregate score.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Signal:
    layer: Layer
    detector_id: str
    category: ThreatCategory
    severity: float
    weight: float
    evidence_span: tuple[int, int] | None = None
    explanation: str = ""
    rule_id: str | None = None
    pattern_id: str | None = None
    sanitize: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError(f"signal severity out of range [0,1]: {self.severity}")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"signal weight out of range [0,1]: {self.weight}")
