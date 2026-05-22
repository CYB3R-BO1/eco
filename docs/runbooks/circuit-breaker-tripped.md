# Circuit breaker tripped

Triggered by the `CircuitBreakerOpen` Prometheus alert when
`ai_security_circuit_breaker_state{agent_name=...} == 2`.

## What is happening

The breaker for an agent/external dependency has crossed the failure
threshold (default 5 consecutive failures in 60 s) and is failing fast
for the next 30 s. The platform continues serving — workflows that
depend on the breaker transition to `DEGRADED` rather than retrying.

## Diagnose

```bash
docker compose logs api | grep "circuit.opened\|circuit.reopened" | tail
```

If the agent is an LLM provider, check
`ai_security_llm_tokens_used_total` for a stalled rate, and the provider
status page. If it's an enrichment provider, inspect
`enrichment_total{status="failure",source="..."}` for the failing
source.

## Mitigate

The breaker self-heals — once the underlying dependency is up,
half-open state allows one probe and closes on success. No operator
action is required to clear the breaker.

If the dependency is permanently down, set the relevant `LLM_API_KEY`
or enrichment provider config to disable that path entirely.
