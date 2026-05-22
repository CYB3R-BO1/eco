# Architecture overview

Backend-first, modular monolith. One Python service running uvicorn,
talking to Postgres + Neo4j + Redis, with OpenTelemetry and Prometheus
exporters. No Kubernetes, no microservices, no frontend dashboards (the
MVP is API-only). The blueprint goes wider; the **MVP** is exactly two
flagship capabilities:

1. **AI-for-Security** — IOC correlation & investigation engine. Ingest
   evidence, extract entities, enrich, correlate in graph, reason over
   evidence with an LLM.
2. **Security-for-AI** — model-agnostic AI firewall. Prompt injection +
   jailbreak detection, risk scoring, block/sanitize decisions.

Phase 1–5 built the capabilities. **Phase 6** is the layer this doc
catalogs: telemetry, auth, RBAC, hardening, retention, backup, CI/CD,
load tests, chaos suite, runbooks.

## Top-level layout

```
apps/api/          FastAPI app, dependencies, middleware, routers
core/              Cross-cutting modules (config, logging, events,
                   security, observability, scheduler, llm)
agents/            LangGraph agent definitions
orchestration/     Runtime: workflows, agent dispatcher, DLQ, retries
firewall/          Prompt analysis pipeline + output validator
investigation/     IOC ingestion, extraction, enrichment, lifecycle
graph/             Graph Service (only writer to Neo4j),
                   governance/validator, correlator
evidence/          Evidence Engine — reference, never embed raw data
resolution/        Entity resolution (canonical forms + alias tracking)
schemas/           Pydantic v2 request/response models
storage/           SQLAlchemy ORM models + Postgres-specific helpers
tests/             unit, integration, load, chaos, observability
infra/             Docker, backup scripts, CI helper scripts
```

## Architectural invariants

Twelve invariants in `CLAUDE.md` are load-bearing — violating them
silently corrupts investigations or the graph. The most security-
critical ones are enforced by tests:

- **#12 (privacy by default)** is enforced by
  `tests/observability/test_no_prompt_leakage.py` — every release runs
  the canary check.
- **#2 (Graph Service is the only writer to Neo4j)** is enforced by
  there being no public Cypher endpoint and the GraphMutator class
  being the single entry point for writes.
- **#1 (canonical event model)** is enforced by the `Event` Pydantic
  model and the INSERT-only `EventEmitter`.

## Phase 6 surface

| Concern                          | Where to look                                        |
|----------------------------------|------------------------------------------------------|
| OTel + Prometheus + log context  | `core/observability/`, `core/logging/context.py`     |
| Auth (HS256 JWT, kid rotation)   | `core/security/jwt.py`, `apps/api/auth.py`           |
| RBAC                             | `core/security/rbac.py`, `apps/api/rbac.py`          |
| Hardening middleware             | `apps/api/middleware_security.py`, `…_body_limit.py`, `…_ratelimit.py`, `…_idempotency.py` |
| Retention + secure deletion      | `core/scheduler/jobs/`                               |
| Backup scripts                   | `infra/backup/`                                      |
| CI/CD                            | `.github/workflows/{ci,release,nightly}.yml`         |
| Load tests                       | `tests/load/locustfile.py`                           |
| Slow-query log                   | `core/database/slow_query_log.py`                    |
| Chaos suite                      | `tests/chaos/`                                       |
| Runbooks                         | `docs/runbooks/`                                     |
