"""Layer 3 — pattern catalog.

A tuple of compiled-regex entries. Each :class:`PatternEntry` has a stable
``pattern_id`` (referenced by rules and audit records), a category, a
severity float in [0, 1], a weight in [0, 1], and a ``sanitize`` flag that
the sanitizer consults to know whether the matching span should be
redacted.

Order *does* matter for sanitization (longer / more specific matches
should fire first so their spans win), but for signal accumulation order
is irrelevant — every match emits its own Signal.

Mirrors the shape of ``investigation/extraction/patterns.py`` so the
codebase has a single "load a regex catalog at import time" idiom.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from firewall.models.signals import Layer, Signal, ThreatCategory


@dataclass(frozen=True)
class PatternEntry:
    pattern_id: str
    pattern: re.Pattern[str]
    category: ThreatCategory
    severity: float
    weight: float
    sanitize: bool = False
    explanation: str = ""


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
# Pattern IDs follow the convention "p.<category>.<short-name>"; never
# reuse one. Adding a pattern requires:
#   1. a unique pattern_id,
#   2. a corresponding fixture entry in tests/fixtures/firewall/* if it
#      represents a new class of attack,
#   3. consideration for whether ``sanitize`` makes sense (only set True
#      when redacting the span produces a still-coherent prompt).

PATTERNS: tuple[PatternEntry, ...] = (
    # ---- direct prompt injection ----------------------------------------
    PatternEntry(
        pattern_id="p.injection.ignore_previous",
        pattern=re.compile(
            r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?"
            r"(?:previous|prior|earlier|above|the)\s+"
            r"(?:instructions?|prompts?|rules?|directives?|context)\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.PROMPT_INJECTION,
        severity=0.92,
        weight=0.95,
        sanitize=True,
        explanation='classic "ignore previous instructions" override',
    ),
    PatternEntry(
        pattern_id="p.injection.system_reveal",
        pattern=re.compile(
            r"\b(?:reveal|print|show|output|repeat|leak|exfiltrate)\s+"
            r"(?:the\s+|your\s+)?(?:system|initial|original|hidden)\s+"
            r"(?:prompt|instructions?|message)\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.PROMPT_INJECTION,
        severity=0.95,
        weight=0.95,
        sanitize=True,
        explanation="system-prompt extraction attempt",
    ),
    PatternEntry(
        pattern_id="p.injection.developer_override",
        pattern=re.compile(
            r"\b(?:developer|admin|root)\s+mode\s+(?:on|enabled|activated)\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.PROMPT_INJECTION,
        severity=0.80,
        weight=0.80,
        sanitize=True,
        explanation="developer/admin-mode override",
    ),

    # ---- jailbreak ------------------------------------------------------
    PatternEntry(
        pattern_id="p.jailbreak.dan",
        pattern=re.compile(
            r"\b(?:do\s+anything\s+now|DAN)\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.JAILBREAK,
        severity=0.90,
        weight=0.90,
        sanitize=True,
        explanation="DAN-family jailbreak",
    ),
    PatternEntry(
        pattern_id="p.jailbreak.no_restrictions",
        pattern=re.compile(
            r"\b(?:you\s+have\s+no\s+restrictions|"
            r"no\s+(?:limits?|rules?|ethics|guidelines)|"
            r"without\s+(?:any\s+)?(?:restrictions?|limits?|filters?))\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.JAILBREAK,
        severity=0.78,
        weight=0.82,
        sanitize=True,
        explanation="restrictions-removal directive",
    ),
    PatternEntry(
        pattern_id="p.jailbreak.pretend_evil",
        pattern=re.compile(
            r"\b(?:pretend|act|role\s*play|simulate)\s+(?:to\s+be\s+|as\s+|you\s+are\s+)?"
            r"(?:an?\s+)?(?:evil|unrestricted|jailbroken|amoral|unfiltered)\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.JAILBREAK,
        severity=0.78,
        weight=0.85,
        sanitize=True,
        explanation="evil-persona role-play",
    ),

    # ---- role manipulation ----------------------------------------------
    PatternEntry(
        pattern_id="p.role.system_tag",
        pattern=re.compile(
            r"<\|im_start\|>\s*system|<\|system\|>|\[\s*system\s*\]|###\s*system\s*:",
            re.IGNORECASE,
        ),
        category=ThreatCategory.ROLE_MANIPULATION,
        severity=0.85,
        weight=0.90,
        sanitize=True,
        explanation="role tag injection",
    ),
    PatternEntry(
        pattern_id="p.role.you_are_now",
        pattern=re.compile(
            r"\byou\s+are\s+now\s+(?:a|an|the)\s+\w+",
            re.IGNORECASE,
        ),
        category=ThreatCategory.ROLE_MANIPULATION,
        severity=0.55,
        weight=0.65,
        sanitize=False,
        explanation='"you are now ..." persona swap',
    ),

    # ---- indirect injection ---------------------------------------------
    PatternEntry(
        pattern_id="p.indirect.markdown_command",
        pattern=re.compile(
            r"\[\s*[^\]]+\s*\]\(\s*(?:javascript|data):",
            re.IGNORECASE,
        ),
        category=ThreatCategory.INDIRECT_INJECTION,
        severity=0.70,
        weight=0.75,
        sanitize=True,
        explanation="javascript: / data: URL in markdown link",
    ),
    PatternEntry(
        pattern_id="p.indirect.hidden_html_comment",
        pattern=re.compile(
            r"<!--.*?(?:ignore|system|prompt|instructions?).*?-->",
            re.IGNORECASE | re.DOTALL,
        ),
        category=ThreatCategory.INDIRECT_INJECTION,
        severity=0.75,
        weight=0.80,
        sanitize=True,
        explanation="instruction-bearing HTML comment",
    ),

    # ---- tool abuse -----------------------------------------------------
    PatternEntry(
        pattern_id="p.tool.function_call_block",
        pattern=re.compile(
            r"<\s*tool[^>]*>.*?<\s*/\s*tool\s*>",
            re.IGNORECASE | re.DOTALL,
        ),
        category=ThreatCategory.TOOL_ABUSE,
        severity=0.70,
        weight=0.70,
        sanitize=True,
        explanation="<tool>…</tool> block in user input",
    ),
    PatternEntry(
        pattern_id="p.tool.shell_command",
        pattern=re.compile(
            r"\b(?:rm\s+-rf|curl\s+[^\s]+\s*\|\s*(?:sh|bash)|nc\s+-l\s+\d+)\b",
        ),
        category=ThreatCategory.TOOL_ABUSE,
        severity=0.85,
        weight=0.85,
        sanitize=True,
        explanation="dangerous shell-command pattern",
    ),

    # ---- data exfiltration ----------------------------------------------
    PatternEntry(
        pattern_id="p.exfil.fetch_external",
        pattern=re.compile(
            r"\b(?:fetch|GET|POST|send|forward)\s+(?:my\s+)?"
            r"(?:secrets?|credentials?|api\s*keys?|env(?:ironment)?|tokens?)"
            r"\s+to\s+https?://",
            re.IGNORECASE,
        ),
        category=ThreatCategory.DATA_EXFILTRATION,
        severity=0.95,
        weight=0.95,
        sanitize=True,
        explanation="explicit credential exfiltration instruction",
    ),
    PatternEntry(
        pattern_id="p.exfil.print_secrets",
        pattern=re.compile(
            r"\b(?:print|show|reveal|dump)\s+(?:all\s+|the\s+)?"
            r"(?:secrets?|credentials?|api\s*keys?|passwords?|env)",
            re.IGNORECASE,
        ),
        category=ThreatCategory.DATA_EXFILTRATION,
        severity=0.80,
        weight=0.80,
        sanitize=True,
        explanation="secret-disclosure directive",
    ),

    # ---- PII (input-side detection; redaction happens in sanitizer/pii) -
    PatternEntry(
        pattern_id="p.pii.email",
        pattern=re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        ),
        category=ThreatCategory.PII_DISCLOSURE,
        severity=0.35,
        weight=0.40,
        sanitize=True,
        explanation="email address",
    ),
    PatternEntry(
        pattern_id="p.pii.aws_key",
        pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        category=ThreatCategory.PII_DISCLOSURE,
        severity=0.90,
        weight=0.90,
        sanitize=True,
        explanation="AWS access key id",
    ),
    PatternEntry(
        pattern_id="p.pii.phone_e164",
        pattern=re.compile(r"\+[1-9]\d{1,14}\b"),
        category=ThreatCategory.PII_DISCLOSURE,
        severity=0.30,
        weight=0.35,
        sanitize=True,
        explanation="E.164 phone number",
    ),
    PatternEntry(
        pattern_id="p.pii.credit_card",
        pattern=re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        category=ThreatCategory.PII_DISCLOSURE,
        severity=0.50,
        weight=0.55,
        sanitize=True,
        explanation="credit-card-shaped digit run",
    ),

    # ---- prompt leakage (input-side: user asking what we'd consider leakage) -
    PatternEntry(
        pattern_id="p.leak.echo_back",
        pattern=re.compile(
            r"\brepeat\s+(?:everything|all)\s+(?:above|before|so\s+far)\b",
            re.IGNORECASE,
        ),
        category=ThreatCategory.PROMPT_LEAKAGE,
        severity=0.60,
        weight=0.65,
        sanitize=False,
        explanation="echo-back instruction (potential prompt-leak vector)",
    ),
)


def detect(normalized_text: str) -> list[Signal]:
    signals: list[Signal] = []
    for entry in PATTERNS:
        for match in entry.pattern.finditer(normalized_text):
            signals.append(
                Signal(
                    layer=Layer.PATTERN,
                    detector_id=entry.pattern_id,
                    category=entry.category,
                    severity=entry.severity,
                    weight=entry.weight,
                    evidence_span=(match.start(), match.end()),
                    explanation=entry.explanation or entry.pattern_id,
                    pattern_id=entry.pattern_id,
                    sanitize=entry.sanitize,
                )
            )
    return signals


def pattern_ids() -> tuple[str, ...]:
    return tuple(entry.pattern_id for entry in PATTERNS)


# Import-time sanity: every entry has a non-empty id and a valid pattern.
_seen: set[str] = set()
for _entry in PATTERNS:
    assert _entry.pattern_id, "PatternEntry.pattern_id must be non-empty"
    assert _entry.pattern_id not in _seen, f"duplicate pattern_id: {_entry.pattern_id}"
    assert 0.0 <= _entry.severity <= 1.0
    assert 0.0 <= _entry.weight <= 1.0
    _seen.add(_entry.pattern_id)
del _seen, _entry
