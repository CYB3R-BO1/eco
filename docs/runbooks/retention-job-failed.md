# Retention job failed

Triggered by `RetentionJobFailed` alert when
`retention_job_runs_total{outcome="error"}` increments.

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
```

## Verify

After the job re-runs, the next observation of
`retention_job_runs_total{outcome="success"}` should increment.
