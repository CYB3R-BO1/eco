# DLQ drain

Triggered by the `dlq-depth-growing` Prometheus alert.

## Diagnose

```bash
docker compose exec postgres psql -U platform -d platform -c "
  SELECT queue_name, count(*) FILTER (WHERE replayed_at IS NULL) AS unresolved,
         count(*) AS total
  FROM dead_letter_entries
  GROUP BY queue_name;
"
```

If `unresolved > 100` for any queue, the dependent service is failing:

- `ENRICHMENT` → an enrichment provider is down. Check
  `circuit_breaker_state{agent_name=~"enrichment.*"}`.
- `GRAPH` → Neo4j is rejecting writes. Check
  `graph_writes_total{op=~".*rejected"}` and
  `graph_schema_violation` log lines.
- `REASONING` → LLM provider is down. Check
  `ai_security_llm_tokens_used_total` for stalled growth.
- `WORKFLOW` → orchestration runtime degraded. Check
  `workflow_runs.status='DEGRADED'`.

## Drain

Once the root cause is fixed, replay the queue:

```bash
docker compose exec api python -m orchestration.dlq.replay \
  --queue ENRICHMENT --batch 50
```

Each replay sets `replayed_at` on the entry; the retention job
(`retention_dlq`) removes resolved rows after 30 days.

## Do not

- Do not delete DLQ rows manually. The replay path is the only
  audit-safe way to clear an entry.
- Do not increase `dlq_resolved_days` to silence the alert. The
  retention job is for *resolved* rows; growing unresolved rows are
  the real signal.
