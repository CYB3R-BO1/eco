"""StubLLM determinism — identical inputs → identical completion text."""
from __future__ import annotations

import pytest

from core.llm.client import StubLLM


@pytest.mark.asyncio
async def test_stub_is_deterministic_on_repeat() -> None:
    llm = StubLLM()
    out1 = await llm.complete(
        prompt_template_id="investigation_summary.v1",
        rendered_prompt="findings: X, Y, Z",
        system_prompt="be brief",
    )
    out2 = await llm.complete(
        prompt_template_id="investigation_summary.v1",
        rendered_prompt="findings: X, Y, Z",
        system_prompt="be brief",
    )
    assert out1.text == out2.text
    assert out1.usage.input == out2.usage.input
    assert out1.usage.output == out2.usage.output


@pytest.mark.asyncio
async def test_stub_completion_differs_per_prompt() -> None:
    llm = StubLLM()
    a = await llm.complete(
        prompt_template_id="t", rendered_prompt="alpha", system_prompt=None
    )
    b = await llm.complete(
        prompt_template_id="t", rendered_prompt="beta", system_prompt=None
    )
    assert a.text != b.text


@pytest.mark.asyncio
async def test_stub_reports_stub_provider() -> None:
    llm = StubLLM()
    out = await llm.complete(
        prompt_template_id="t", rendered_prompt="x", system_prompt=None
    )
    assert out.provider == "stub"
    assert out.finish_reason == "stop"
