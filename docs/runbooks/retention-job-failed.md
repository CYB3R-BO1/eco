# Retention job failed

Triggered by `RetentionJobFailed` alert when
`retention_job_runs_total{outcome="error"}` increments.

## Jobs in scope

| Job | TTL setting | Default | Purpose |
|---|---|---|---|
| `retention_evidence` | `retention.evidence_days` (by provenance) | PRIMARY 180d → AI_GENERATED 30d | Evidence table by provenance level |
| `retention_events` | `retention.investigation_events_days` | 90d | `investigation_events` audit rows |
| `retention_audit` | `retention.audit_log_days` | 365d | `audit_log` rows |
| `retention_workflow` | `retention.workflow_runs_days` | 60d | `workflow_runs` history |
| `retention_idempotency` | `retention.idempotency_keys_hours` | 24h | `idempotency_keys` short-TTL cache (Phase 7 WP2) |

`retention_idempotency` fires at the same cron as the others but offset
by +15 min to avoid lock-step contention. It uses the same
`pg_try_advisory_lock` primitive and the same `outcome="error"` metric
on failure.

## Diagnose

```bash
docker compose logs api | grep "retention\." | tail -40
```

Look for the failing job (each emits a structured log line on
exception). Common causes:

- FK cascade rejected the delete — a child table still references a
  row the job tried to remove. Patch the schema or extend the delete
  to chain.
- Lock contention — the `pg_advisory_lock` held the lock for too long
  and another connection got starved. Re-run; APScheduler will fire
  again next tick.
- Connection pool exhaustion — the retention DELETE runs in its own
  session; pool starvation means another path is leaking sessions.

## Mitigate

The retention scheduler retries on the next cron tick (default daily
02:30 UTC). For an urgent forced run:

```bash
make retention-dryrun                  # preview the planned counts
docker compose exec api python -m core.scheduler.jobs.retention_evidence
docker compose exec api python -m core.scheduler.jobs.retention_idempotency
```

## Verify

After the job re-runs, the next observation of
`retention_job_runs_total{outcome="success"}` should increment.
