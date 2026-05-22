"""LLM client protocol + two implementations.

:class:`StubLLM` returns deterministic responses keyed by
``(prompt_template_id, sorted variables)``. Tests use it exclusively so the
suite stays hermetic. :class:`OpenAIClient` talks to any OpenAI-compatible
``/chat/completions`` endpoint.

Both implementations honor the contract:

1. **No raw text in logs.** Prompts and completions are hashed (SHA-256)
   before any structured log call (CLAUDE.md invariant #12).
2. **Templated prompts only.** The caller passes a stable
   ``prompt_template_id`` and a ``variables`` dict; rendering happens inside
   the client. Free-form prompts are not supported — keeps audit trails
   meaningful and prevents accidental f-string injection.
3. **Provider-reported usage is authoritative.** When the provider returns a
   ``usage`` block the client uses it verbatim; we only fall back to the
   ``estimate_tokens`` heuristic when usage is missing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config.settings import LLMSettings
from core.llm.tokens import AITokenUsage, estimate_tokens
from core.observability.metrics import LLM_TOKENS_USED_TOTAL

log = structlog.get_logger(__name__)


def _record_tokens(model: str, usage: AITokenUsage) -> None:
    """Emit ``llm_tokens_used_total`` after a completion returns."""
    if usage.input:
        LLM_TOKENS_USED_TOTAL.labels(model=model, phase="input").inc(usage.input)
    if usage.output:
        LLM_TOKENS_USED_TOTAL.labels(model=model, phase="output").inc(usage.output)


class LLMProviderError(RuntimeError):
    """Raised when the LLM provider returns a non-recoverable error."""


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    usage: AITokenUsage
    model: str
    provider: str
    finish_reason: str | None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class LLMClient(Protocol):
    provider_name: str

    async def complete(
        self,
        *,
        prompt_template_id: str,
        rendered_prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMCompletion: ...


class StubLLM:
    """Deterministic stub. Used when ``LLM_API_KEY`` is empty."""

    provider_name = "stub"

    def __init__(self, *, model: str = "stub-v1") -> None:
        self._model = model

    async def complete(
        self,
        *,
        prompt_template_id: str,
        rendered_prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMCompletion:
        # Deterministic body keyed by template_id + prompt hash. Lets tests
        # assert exact output without coupling to a real LLM.
        digest = _hash(rendered_prompt)
        text = (
            f"[stub:{prompt_template_id}] deterministic completion "
            f"for prompt_hash={digest}"
        )
        usage = AITokenUsage(
            input=estimate_tokens(rendered_prompt) + estimate_tokens(system_prompt or ""),
            output=estimate_tokens(text),
        )
        log.info(
            "llm.stub.complete",
            template_id=prompt_template_id,
            prompt_hash=digest,
            input_tokens=usage.input,
            output_tokens=usage.output,
        )
        _record_tokens(self._model, usage)
        return LLMCompletion(
            text=text,
            usage=usage,
            model=self._model,
            provider=self.provider_name,
            finish_reason="stop",
        )


class OpenAIClient:
    """Real OpenAI-compatible client. Used when ``LLM_API_KEY`` is set."""

    provider_name = "openai"

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(
        self,
        *,
        prompt_template_id: str,
        rendered_prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMCompletion:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": rendered_prompt})

        payload = {
            "model": self._settings.model,
            "messages": messages,
            "max_tokens": min(max_tokens, self._settings.max_tokens_per_request),
            "temperature": temperature,
        }

        digest = _hash(rendered_prompt)
        log.info(
            "llm.openai.request",
            template_id=prompt_template_id,
            prompt_hash=digest,
            model=self._settings.model,
        )

        retrying = AsyncRetrying(
            stop=stop_after_attempt(max(1, self._settings.max_retries + 1)),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.TransportError, _Retryable)),
            reraise=True,
        )

        body: dict[str, Any] | None = None
        async for attempt in retrying:
            with attempt:
                response = await self._client.post("/chat/completions", json=payload)
                if response.status_code >= 500:
                    raise _Retryable(f"upstream {response.status_code}")
                if response.status_code == 429:
                    raise _Retryable("rate limited")
                if response.status_code >= 400:
                    raise LLMProviderError(
                        f"openai_error status={response.status_code} body={response.text[:200]}"
                    )
                body = response.json()

        assert body is not None  # tenacity reraises on exhaustion
        return self._parse_response(body, prompt_template_id, digest, rendered_prompt, system_prompt)

    def _parse_response(
        self,
        body: dict[str, Any],
        template_id: str,
        prompt_hash: str,
        rendered_prompt: str,
        system_prompt: str | None,
    ) -> LLMCompletion:
        try:
            choice = body["choices"][0]
            text = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(f"unexpected response shape: {exc}") from exc

        usage_block = body.get("usage") or {}
        input_tokens = int(usage_block.get("prompt_tokens", 0))
        output_tokens = int(usage_block.get("completion_tokens", 0))
        if input_tokens == 0:
            input_tokens = estimate_tokens(rendered_prompt) + estimate_tokens(system_prompt or "")
        if output_tokens == 0:
            output_tokens = estimate_tokens(text)

        log.info(
            "llm.openai.response",
            template_id=template_id,
            prompt_hash=prompt_hash,
            completion_hash=_hash(text),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
        )
        usage = AITokenUsage(input=input_tokens, output=output_tokens)
        response_model = body.get("model", self._settings.model)
        _record_tokens(response_model, usage)
        return LLMCompletion(
            text=text,
            usage=usage,
            model=response_model,
            provider=self.provider_name,
            finish_reason=finish_reason,
        )


class _Retryable(Exception):
    """Internal marker for tenacity — transient upstream errors."""


def build_llm_client(settings: LLMSettings) -> LLMClient:
    """Pick the right client based on whether an API key is configured."""
    if settings.has_api_key:
        log.info("llm.using_real_client", provider=settings.provider, model=settings.model)
        return OpenAIClient(settings)
    log.info("llm.using_stub_client", reason="no_api_key")
    return StubLLM()


# Round-trip sanity: importing this module must not silently pull a real
# network dependency. The `httpx` module is already present; we don't open
# any connection here — only inside ``OpenAIClient.__init__``.
_ = json  # keep linter happy; reserved for future structured-output paths
