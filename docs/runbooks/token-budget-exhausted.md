# Token budget exhausted

The platform caps LLM spend per investigation via
`LLM_MAX_TOKENS_PER_INVESTIGATION` (default 50,000). When breached the
reasoning agent raises `TokenBudgetExceededError` and the API returns
`429`.

## Diagnose

```bash
docker compose logs api | grep llm.token_budget_exceeded | tail
```

The log line names the investigation ID and remaining budget. Cross-
reference with `ai_security_llm_tokens_used_total{model="..."}` to see
which model is burning budget.

## Mitigate

For a one-off spike, raise the budget for that investigation only by
clearing the Redis counter (the budget is investigation-scoped):

```bash
docker compose exec redis redis-cli DEL investigation:tokens:<id>
```

For a systemic increase (the workload outgrew the default), bump
`LLM_MAX_TOKENS_PER_INVESTIGATION` in env and restart.

## Do not

- Do not silently degrade to a local LLM (invariant #10 forbids it).
  When the AI tier is exhausted, the investigation transitions to
  `AI_UNAVAILABLE` and the deterministic findings remain authoritative.
