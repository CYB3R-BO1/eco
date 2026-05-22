# Incident response

Generic structure for triaging any production alert. Specific playbooks
live alongside this file (`dlq-drain.md`, `circuit-breaker-tripped.md`,
etc.) — start there if the alert maps to one.

## 1. Confirm scope

- Open the Grafana dashboard `Platform — Phase 6`
  (`docs/observability/dashboards/grafana-platform.json`).
- Pull recent error rate: `sum by (route)(rate(http_requests_total{status=~"5.."}[5m]))`.
- Tail logs: `docker compose logs -f api | grep -i error`.

## 2. Capture state for postmortem

Before mitigating, snapshot anything volatile:

```bash
curl -s http://127.0.0.1:9090/metrics > /tmp/incident-metrics.txt
docker compose logs api > /tmp/incident-api-logs.txt
docker compose exec postgres pg_dump --schema=public -t investigation_events \
  platform > /tmp/incident-events.sql
```

## 3. Mitigate

Mitigation order is **least destructive first**:

1. Restart a single service: `docker compose restart api`.
2. Scale back if traffic is the cause: drop `RATE_LIMIT_DEFAULT`.
3. Quarantine: stop ingest with `SECURITY_BOOTSTRAP_ADMIN_SECRET=`
   unset (locks `/tokens/issue`) plus revoke existing kids via
   `/tokens/rotate-key`.
4. Restore: only if data integrity is suspected — see
   `backup-restore.md`.

## 4. Postmortem

Write the report against the captured artefacts. Update CLAUDE.md
invariants if a new class of failure was found.
