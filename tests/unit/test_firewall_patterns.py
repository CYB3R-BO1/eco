"""Pattern-catalog detection.

The headline contract: every entry in ``jailbreaks.json`` and
``injections.json`` produces at least one HIGH-severity Signal in the
expected category, and every entry in ``benign.json`` produces zero
HIGH-severity signals.
"""
from __future__ import annotations

import json
from pathlib import Path

from firewall.analysis import patterns
from firewall.analysis.normalization import normalize
from firewall.models.signals import ThreatCategory


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "firewall"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def test_pattern_ids_are_unique_and_nonempty() -> None:
    ids = patterns.pattern_ids()
    assert len(ids) == len(set(ids))
    assert all(pid and pid.startswith("p.") for pid in ids)


def test_jailbreak_corpus_each_hits_expected_category() -> None:
    for entry in _load("jailbreaks.json"):
        r = normalize(entry["prompt"])
        signals = patterns.detect(r.text)
        cats = {s.category for s in signals}
        expected = {ThreatCategory(c) for c in entry["expected_categories"]}
        assert expected & cats, (
            f"{entry['id']!r} expected any of {expected} but got {cats}"
        )


def test_injection_corpus_each_hits_expected_category() -> None:
    for entry in _load("injections.json"):
        r = normalize(entry["prompt"])
        signals = patterns.detect(r.text)
        cats = {s.category for s in signals}
        expected = {ThreatCategory(c) for c in entry["expected_categories"]}
        assert expected & cats, (
            f"{entry['id']!r} expected any of {expected} but got {cats}"
        )


def test_benign_corpus_emits_no_high_severity_threat_signals() -> None:
    benign_high_severity_cats = {
        ThreatCategory.PROMPT_INJECTION,
        ThreatCategory.JAILBREAK,
        ThreatCategory.DATA_EXFILTRATION,
    }
    for entry in _load("benign.json"):
        r = normalize(entry["prompt"])
        signals = patterns.detect(r.text)
        high = [s for s in signals if s.category in benign_high_severity_cats and s.severity >= 0.70]
        assert not high, f"{entry['id']!r} produced high-severity signals: {high}"
