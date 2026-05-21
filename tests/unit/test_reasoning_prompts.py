"""Reasoning prompt templates: variable-binding hygiene."""
from __future__ import annotations

import pytest

from agents.reasoning.prompts import PROMPT_TEMPLATES


def test_investigation_summary_template_registered() -> None:
    assert "investigation_summary.v1" in PROMPT_TEMPLATES


def test_template_render_succeeds_with_all_variables() -> None:
    tmpl = PROMPT_TEMPLATES["investigation_summary.v1"]
    rendered = tmpl.render(
        {
            "investigation_id": "1234",
            "finding_count": "2",
            "findings_block": "[0] x\n[1] y",
        }
    )
    assert "1234" in rendered
    assert "[0] x" in rendered


def test_template_render_raises_on_missing_variable() -> None:
    tmpl = PROMPT_TEMPLATES["investigation_summary.v1"]
    with pytest.raises(ValueError, match="missing variables"):
        tmpl.render({"investigation_id": "x"})


def test_template_id_has_version_suffix() -> None:
    """Audit-friendly: every template ID ends with .vN so rotation is explicit."""
    for tid in PROMPT_TEMPLATES.keys():
        assert ".v" in tid, f"template {tid!r} lacks a version suffix"
