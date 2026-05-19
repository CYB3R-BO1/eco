"""Output-validator behavior on curated fixtures."""
from __future__ import annotations

import json
from pathlib import Path

from firewall.output_validation.validator import OutputValidator
from firewall.policy.policy import FirewallPolicy

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "firewall"


def _policy() -> FirewallPolicy:
    return FirewallPolicy(
        block_threshold=0.85,
        sanitize_threshold=0.65,
        review_threshold=0.40,
        finding_weight_floor=0.5,
    )


def test_output_corpus_outcomes_match_fixtures() -> None:
    validator = OutputValidator(_policy())
    for entry in json.loads((FIXTURES / "output_leakage.json").read_text()):
        report = validator.validate(entry["response"])
        assert report.result.value == entry["expected_outcome"], (
            f"{entry['id']!r}: expected {entry['expected_outcome']}, "
            f"got {report.result.value} (findings={report.findings})"
        )


def test_pii_response_is_sanitized_with_redactions() -> None:
    validator = OutputValidator(_policy())
    report = validator.validate("Contact me at alice@example.com.")
    assert report.result.value == "SANITIZE"
    assert report.sanitized_response is not None
    assert "[EMAIL]" in report.sanitized_response


def test_benign_response_passes() -> None:
    validator = OutputValidator(_policy())
    report = validator.validate("Paris is the capital of France.")
    assert report.result.value == "PASS"
    assert report.sanitized_response is None
