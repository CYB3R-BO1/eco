"""Sanitizer — turn a (normalized prompt, signal list) into a cleaned
prompt plus an audit trail of redactions.

Algorithm:

1. Collect every Signal where ``sanitize=True`` AND ``evidence_span``
   is set (whole-prompt signals like "long" can't be span-redacted).
2. Sort spans by start offset; merge overlapping spans (longer one wins,
   so we never produce double-redacted ``[REDACTED][REDACTED]`` runs).
3. Walk left-to-right, copying original text up to each span's start and
   emitting the replacement marker. Track an offset delta so the
   resulting :class:`Redaction` records reference the *original*
   normalized text offsets, not the post-replacement offsets.
4. PII patterns get marker strings keyed on their pattern_id
   (``p.pii.email`` → ``[EMAIL]``); generic pattern signals get
   ``[REDACTED:<pattern_id>]``; rule signals get ``[REDACTED:<rule_id>]``.

The sanitizer never invents content. Every redaction shrinks or preserves
length — it cannot extend the prompt.
"""
from __future__ import annotations

from firewall.models.reports import Redaction
from firewall.models.signals import Signal

_PII_MARKERS: dict[str, str] = {
    "p.pii.email": "[EMAIL]",
    "p.pii.aws_key": "[AWS_KEY]",
    "p.pii.phone_e164": "[PHONE]",
    "p.pii.credit_card": "[CC]",
}

_ROLE_MARKER = "[ROLE_TAG_REMOVED]"
_TOOL_MARKER = "[TOOL_CALL_REMOVED]"


def apply(
    normalized_text: str,
    signals: list[Signal],
) -> tuple[str, tuple[Redaction, ...]]:
    """Apply sanitization. Returns ``(cleaned_text, redactions)``.

    ``redactions`` references offsets into ``normalized_text`` — the
    caller can correlate them with the prompt fingerprint to audit
    exactly what was removed.
    """
    spans: list[tuple[int, int, str, str, str]] = []
    for s in signals:
        if not s.sanitize or s.evidence_span is None:
            continue
        start, end = s.evidence_span
        if start < 0 or end <= start or end > len(normalized_text):
            continue
        replacement = _marker_for(s)
        rule_or_pattern = s.rule_id or s.pattern_id or s.detector_id
        spans.append((start, end, replacement, rule_or_pattern, s.explanation))

    if not spans:
        return normalized_text, ()

    merged = _merge_overlapping(sorted(spans, key=lambda x: (x[0], -(x[1] - x[0]))))

    parts: list[str] = []
    redactions: list[Redaction] = []
    cursor = 0
    for start, end, replacement, rule_id, reason in merged:
        if cursor < start:
            parts.append(normalized_text[cursor:start])
        parts.append(replacement)
        redactions.append(
            Redaction(
                start=start,
                end=end,
                rule_id=rule_id,
                replacement=replacement,
                reason=reason or rule_id,
            )
        )
        cursor = end
    if cursor < len(normalized_text):
        parts.append(normalized_text[cursor:])

    return "".join(parts), tuple(redactions)


def _marker_for(signal: Signal) -> str:
    if signal.pattern_id and signal.pattern_id in _PII_MARKERS:
        return _PII_MARKERS[signal.pattern_id]
    if signal.pattern_id == "p.role.system_tag" or signal.detector_id == "heuristic.role_tag_density":
        return _ROLE_MARKER
    if signal.pattern_id and signal.pattern_id.startswith("p.tool."):
        return _TOOL_MARKER
    label = signal.rule_id or signal.pattern_id or signal.detector_id
    return f"[REDACTED:{label}]"


def _merge_overlapping(
    spans: list[tuple[int, int, str, str, str]],
) -> list[tuple[int, int, str, str, str]]:
    out: list[tuple[int, int, str, str, str]] = []
    for span in spans:
        if not out:
            out.append(span)
            continue
        prev = out[-1]
        if span[0] < prev[1]:
            # Overlap — keep the wider span (which we sorted to come first).
            if span[1] > prev[1]:
                out[-1] = (prev[0], span[1], prev[2], prev[3], prev[4])
            continue
        out.append(span)
    return out
