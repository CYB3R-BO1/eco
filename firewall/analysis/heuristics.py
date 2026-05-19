"""Layer 2 — heuristic detectors.

Cheap, language-agnostic signals that don't require regex specificity.
Each detector returns a :class:`Signal` or ``None``; the registry runs
them all and accumulates non-``None`` results.

The detectors are deliberately conservative on severity. Heuristics catch
*shape* anomalies (long prompts, mostly-non-ASCII, role-tag-dense). They
are corroborating evidence — never on their own a BLOCK trigger.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Callable

from firewall.analysis.normalization import NormalizationResult
from firewall.models.signals import Layer, Signal, ThreatCategory

# A "long" prompt is the 95th-percentile of typical chat input — anything
# beyond suggests automated payload injection or a context-flood attempt.
_LONG_PROMPT_BYTES = 8_000

# Role-tag tokens we count separately from the pattern layer's role
# matchers; the heuristic just looks at density.
_ROLE_TAG_TOKENS: tuple[str, ...] = (
    "<|im_start|>",
    "<|im_end|>",
    "</s>",
    "<s>",
    "[INST]",
    "[/INST]",
    "### system",
    "### user",
    "### assistant",
    "system:",
    "assistant:",
)
_ROLE_TAG_RE = re.compile(
    "|".join(re.escape(t) for t in _ROLE_TAG_TOKENS),
    re.IGNORECASE,
)

_NON_ASCII_RATIO_THRESHOLD = 0.40
_ENTROPY_THRESHOLD = 4.5  # bits per char — printable text is usually ~3.5–4.0
_MIN_ENTROPY_LEN = 200    # entropy on short strings is noisy


def evaluate(result: NormalizationResult) -> list[Signal]:
    signals: list[Signal] = []
    for detector in _DETECTORS:
        sig = detector(result)
        if sig is not None:
            signals.append(sig)
    return signals


def _detect_long_prompt(r: NormalizationResult) -> Signal | None:
    if r.normalized_length <= _LONG_PROMPT_BYTES:
        return None
    over = r.normalized_length - _LONG_PROMPT_BYTES
    severity = min(0.5, 0.2 + over / 32_000)
    return Signal(
        layer=Layer.HEURISTIC,
        detector_id="heuristic.long_prompt",
        category=ThreatCategory.CONTEXT_POISONING,
        severity=severity,
        weight=0.4,
        explanation=f"prompt length {r.normalized_length} bytes exceeds {_LONG_PROMPT_BYTES}",
        metadata={"length": r.normalized_length},
    )


def _detect_role_tag_density(r: NormalizationResult) -> Signal | None:
    hits = list(_ROLE_TAG_RE.finditer(r.text))
    if not hits:
        return None
    count = len(hits)
    # One stray "system:" in a long sentence shouldn't fire; three+ is suspicious.
    if count < 2 and r.normalized_length > 200:
        return None
    severity = min(0.95, 0.4 + 0.15 * count)
    span = (hits[0].start(), hits[-1].end())
    return Signal(
        layer=Layer.HEURISTIC,
        detector_id="heuristic.role_tag_density",
        category=ThreatCategory.ROLE_MANIPULATION,
        severity=severity,
        weight=0.85,
        evidence_span=span,
        explanation=f"{count} role-tag tokens in prompt",
        metadata={"count": count},
        sanitize=True,
    )


def _detect_non_ascii_ratio(r: NormalizationResult) -> Signal | None:
    if not r.text:
        return None
    non_ascii = sum(1 for ch in r.text if ord(ch) > 127)
    ratio = non_ascii / max(1, len(r.text))
    if ratio < _NON_ASCII_RATIO_THRESHOLD:
        return None
    return Signal(
        layer=Layer.HEURISTIC,
        detector_id="heuristic.non_ascii_ratio",
        category=ThreatCategory.OTHER,
        severity=min(0.5, ratio),
        weight=0.30,
        explanation=f"{ratio:.0%} non-ASCII characters",
        metadata={"ratio": ratio},
    )


def _detect_entropy(r: NormalizationResult) -> Signal | None:
    if r.normalized_length < _MIN_ENTROPY_LEN:
        return None
    entropy = _shannon_entropy(r.text)
    if entropy < _ENTROPY_THRESHOLD:
        return None
    return Signal(
        layer=Layer.HEURISTIC,
        detector_id="heuristic.high_entropy",
        category=ThreatCategory.DATA_EXFILTRATION,
        severity=min(0.6, (entropy - _ENTROPY_THRESHOLD) / 2.0 + 0.3),
        weight=0.35,
        explanation=f"prompt entropy {entropy:.2f} bits/char ≥ {_ENTROPY_THRESHOLD}",
        metadata={"entropy": entropy},
    )


def _detect_deep_encoding(r: NormalizationResult) -> Signal | None:
    if not r.deep_encoding:
        return None
    return Signal(
        layer=Layer.HEURISTIC,
        detector_id="heuristic.deep_encoding",
        category=ThreatCategory.INDIRECT_INJECTION,
        severity=0.7,
        weight=0.7,
        explanation=f"unwrapped through {len(r.encoding_chain)} encoding layers ({list(r.encoding_chain)})",
        metadata={"chain": list(r.encoding_chain)},
    )


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


_DETECTORS: tuple[Callable[[NormalizationResult], Signal | None], ...] = (
    _detect_long_prompt,
    _detect_role_tag_density,
    _detect_non_ascii_ratio,
    _detect_entropy,
    _detect_deep_encoding,
)


def detector_ids() -> Iterable[str]:
    """Stable list of all heuristic detector IDs (for tests + docs)."""
    return (
        "heuristic.long_prompt",
        "heuristic.role_tag_density",
        "heuristic.non_ascii_ratio",
        "heuristic.high_entropy",
        "heuristic.deep_encoding",
    )
