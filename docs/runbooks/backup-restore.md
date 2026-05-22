# Backup & Restore

**RPO target:** 15 minutes. **RTO target:** 1 hour.

The platform has three persistent stores: Postgres (authoritative — events, evidence, audit), Neo4j (derived — rebuildable from Postgres event replay), and Redis (caches + DLQs — rebuildable from cold start). Backup priority is therefore Postgres ≫ Neo4j ≫ Redis.

## Routine backup

```bash
make backup            # both stores
make backup-pg         # Postgres only
make backup-neo4j      # Neo4j only
```

The Postgres dump lands in `./backups/postgres-<timestamp>.dump`. Treat this file the same as the live database — same encryption-at-rest, same access control.

## Restore — fast path (PG)

When the production database is lost and the latest dump is recent enough to meet RPO:

```bash
docker compose down -v
docker compose up -d postgres
make restore-pg FILE=backups/postgres-20260520T0230Z.dump
docker compose up -d
```

## Restore — fast path (Neo4j)

The fast restore uses the Neo4j dump:

```bash
make restore-neo4j FILE=/var/lib/neo4j/import/neo4j.dump
docker compose restart neo4j
```

## Restore — primary path (rebuild graph from PG events)

**This is the load-bearing recovery procedure.** CLAUDE.md invariant #6 says the graph is append-only — its source of truth is `investigation_events` in Postgres. Rebuilding the graph from event replay guarantees consistency with the rest of the system.

1. Restore Postgres as above.
2. Drop the Neo4j database:
   ```bash
   docker compose exec neo4j cypher-shell -u neo4j -p platform_neo4j \
     "MATCH (n) DETACH DELETE n"
   ```
3. Replay events through the existing graph correlator (Phase 3). A
   minimal driver script lives at `infra/scripts/replay_events.py` and
   reads each `GRAPH_NODE_CREATED` / `GRAPH_RELATIONSHIP_CREATED` event
   in timestamp order, dispatching to the same `GraphService` writer.

## Verification

After every restore:

```bash
docker compose exec api alembic current     # confirm migrations applied
docker compose exec api pytest tests/integration/test_graph_correlation.py -q
curl -fsS http://localhost:8000/ready
```

## Backup retention

Local dumps under `./backups/` are operator-managed. Production deployments should ship dumps to S3 (or equivalent) with lifecycle rules matching the retention TTLs in `RetentionSettings`.
