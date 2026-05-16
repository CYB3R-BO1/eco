# AI-Native Cybersecurity & AI Safety Platform

Phase 1 — Foundation. A backend-first modular monolith on FastAPI, PostgreSQL, Neo4j, Redis, and Docker. LangGraph orchestration, agents, the Investigation Engine, and the AI Firewall land in later phases.

For the long-term vision see `BLUEPRINT.md`. For the authoritative MVP execution plan see `PLAN.md`. Architectural invariants every contributor must respect are in `CLAUDE.md`.

## Quickstart

Prerequisites: Docker Desktop (with Docker Compose v2). Python 3.12 only needed for host-side linting; everything runs inside containers otherwise.

```bash
cp .env.example .env
docker compose up -d --build
```

The api container waits on healthchecks for Postgres, Redis, and Neo4j, so the first build takes ~30s before `8000` is listening. Verify:

```bash
curl http://localhost:8000/health        # static OK
curl -i http://localhost:8000/ready      # 200 once Postgres + Redis + Neo4j all green
open http://localhost:8000/docs          # Swagger UI (disabled in production)
open http://localhost:7474               # Neo4j Browser (neo4j / platform_neo4j)
```

`X-Correlation-ID` flows end-to-end: pass one on the request and it'll appear on the response *and* on every JSON log line that route emits (`docker compose logs api`).

## Project layout

```
apps/api          FastAPI app, middleware, routers, lifespan, dependency injection
core/             config, structlog setup, async DB engine, Redis client, OTel scaffold
graph/            Neo4j driver wrapper + Graph Service (the only writer to Neo4j)
schemas/          API request/response Pydantic models
storage/          ORM models (populated from Phase 2 onward)
alembic/          async migration runner; DSN comes from core.config
tests/            unit + integration (integration deferred to docker-compose runs)
infra/            deployment scaffolding (populated in later phases)
```

## Common commands

```bash
make up               # build + start (hot reload enabled)
make down             # stop
make logs             # tail api logs
make api              # bash into the api container
make migrate          # alembic upgrade head
make revision m="add foo"   # autogenerate revision
make test             # pytest inside the container
make lint             # ruff check
make format           # black + ruff --fix
make type-check       # mypy
make clean            # docker compose down -v  (drops volumes!)
```

Without `make` substitute the equivalent `docker compose …` invocations.

## Architectural ground rules

This scaffold is deliberately spare, but several patterns are load-bearing. See `CLAUDE.md` for the full list; the highlights:

1. **Graph Service is the only writer to Neo4j.** Direct driver use outside `graph/graph_service/` is an invariant violation. Phase 1's service is a stub; Phase 2+ adds the schema validation, Relationship Matrix, entity resolution, and evidence-linkage requirements on top.
2. **Lifecycle-managed singletons.** `Database`, `RedisClient`, `Neo4jClient`, `GraphService` live on `app.state` and are accessed via `Depends()` providers from `apps/api/dependencies.py`. Don't reach into module-level globals.
3. **Settings are typed and cached.** New configuration goes in `core/config/settings.py`. Never call `os.environ` directly elsewhere.
4. **Logging is structured.** Use `structlog.get_logger(__name__)`. Correlation IDs and (later) investigation/workflow IDs are bound automatically by middleware.
5. **Migrations pull DSN from `core.config`.** Don't duplicate connection info into `alembic.ini`.

## What's next

Phase 2 (IOC Engine) starts adding ORM models under `storage/postgres/models/`, Cypher fragments under `graph/queries/`, and ingestion/extraction routers under `apps/api/routers/v1/`. Each Alembic revision is generated against `core.database.base.Base.metadata`, so as long as new models are imported in `storage/postgres/models/__init__.py` they'll be picked up by `make revision`.
