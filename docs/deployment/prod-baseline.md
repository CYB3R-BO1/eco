# Production baseline (single-VM compose)

Phase 6 ships as a modular monolith on Docker Compose. The target is a
single VM with enough RAM for the data tier — no Kubernetes, no
autoscaling, no managed services.

## Image

Use the GHCR-published image from `release.yml`:

```
ghcr.io/<owner>/ai-security-platform:<tag>
```

Verify the cosign signature before pulling into a production node:

```bash
cosign verify ghcr.io/<owner>/ai-security-platform:<tag> \
  --certificate-identity-regexp '^https://github\.com/<owner>/.+'
```

## Required env

| Var                                  | Notes                                                 |
|--------------------------------------|-------------------------------------------------------|
| `POSTGRES_HOST`, `_PORT`, `_USER`, `_DB`, `_PASSWORD` | Managed Postgres or local container |
| `NEO4J_URI`, `_USER`, `_PASSWORD`    | bolt:// URL                                           |
| `REDIS_HOST`, `_PORT`                | TLS Redis recommended for prod                        |
| `SECURITY_JWT_KEYS`                  | JSON: `[{"kid":"…","secret":"…"}]` — first kid is active |
| `SECURITY_BOOTSTRAP_ADMIN_SECRET`    | Long random string; gates `/tokens/issue`             |
| `OBSERVABILITY_OTEL_ENABLED`         | `true` in prod                                        |
| `OBSERVABILITY_OTLP_ENDPOINT`        | gRPC URL of your collector (Jaeger/Tempo/Honeycomb)   |
| `OBSERVABILITY_METRICS_BIND_HOST`    | `0.0.0.0` only if scraped from another host           |
| `RETENTION_DRY_RUN`                  | `false` in prod                                       |
| `LLM_API_KEY`                        | If running the AI agents; empty → stub mode           |

Secrets never go into a `.env` committed to git. Use the host's secret
manager (Vault, AWS Secrets Manager, SOPS-encrypted file) and inject at
container start.

## Compose overlay

Add a `docker-compose.prod.yml` overlay that:

- Sets `read_only: true` on the `api` service (the dev overlay can't
  because of the source bind-mount; prod doesn't need it).
- Removes the source bind-mount.
- Adds resource limits (`mem_limit`, `cpus`).
- Mounts the secret store paths read-only.
- Disables the host port mappings except `8000` (the API).

The metrics server stays bound to `127.0.0.1:9090`; reverse-proxy it
via the same node's Prometheus agent.

## Health checks

- `GET /health` (cheap) for load-balancer probes.
- `GET /ready` (deep) for cold-start gating — only flips green once
  Postgres + Neo4j + Redis are all healthy.

## Backups

See `docs/runbooks/backup-restore.md`. RPO 15 min, RTO 1 h. The graph
is rebuilt from Postgres event replay as the primary recovery path.

## Connection pool sizing

`POSTGRES_POOL_SIZE` (default 10) and `POSTGRES_MAX_OVERFLOW` (default 20)
give 30 max connections per process. With the default uvicorn
`--workers 4` and average concurrency of ~8 sessions per worker during
ingest bursts, the pool runs at ~80% saturation under nominal load and
spills to overflow during spikes.

Sizing formula:
```
pool_size + max_overflow ≥ workers × peak_concurrent_sessions
```

If you raise `--workers`, raise `POSTGRES_POOL_SIZE` proportionally and
verify your Postgres instance's `max_connections` (default 100) covers
all uvicorn processes × pool_size. Connection saturation surfaces as
slow `db.session_acquire` log lines and high p99 latency without a
matching `db.slow_query`.

The firewall decision flow holds a PG session across multiple Neo4j
MERGEs in the graph correlator step (one session per
`_persist_decision`). Under sustained Neo4j slowness this is the most
likely place to see pool exhaustion — monitor `postgres.healthcheck`
failures and Neo4j p99 together when sizing.
