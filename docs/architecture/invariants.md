# Architectural invariants

`CLAUDE.md` is the source of truth. This doc summarises which invariant
is enforced where, so a reviewer can map a code change back to the
guarantee it touches.

| #  | Invariant                                       | Enforcement point                                                     |
|----|-------------------------------------------------|-----------------------------------------------------------------------|
| 1  | Canonical event model (immutable, INSERT-only)  | `core/events/emitter.py` (no UPDATE/DELETE methods exposed)           |
| 2  | Graph Service is the only writer to Neo4j       | `graph/graph_service/mutations.py:GraphMutator` — single entry point  |
| 3  | Entity Resolution before graph writes           | `investigation/ingestion/pipeline.py` calls resolver then mutator     |
| 4  | Evidence Engine: reference, don't embed         | Models reference `evidence_id` UUIDs; no JSONB raw blobs in audit     |
| 5  | Deterministic / AI layers separate              | Reasoning agent stores findings via Evidence Engine, never overwrites |
| 6  | Confidence propagated, never assumed            | `graph/graph_service/mutations.py` writes `confidence` on every edge  |
| 7  | Investigation lifecycle is an explicit FSM      | `investigation/lifecycle/manager.py:LifecycleManager.transition`      |
| 8  | Idempotency on retries                          | `storage/postgres/models/idempotency_key.py` + per-route guards       |
| 9  | Bounded memory + operational limits             | `core/config/settings.py:OrchestrationSettings`                       |
| 10 | Failure handling is explicit, not optimistic    | `orchestration/retry/`, `orchestration/dlq/`                          |
| 11 | RBAC checks every (role, resource, action)      | `core/security/rbac.py:ROLE_MATRIX` + `apps/api/rbac.py:requires`     |
| 12 | Privacy by default                              | `core/security/hashing.py` + `tests/observability/test_no_prompt_leakage.py` |

The test in row 12 is the **load-bearing canary** for the privacy
guarantee — any future change that logs raw prompt/evidence text causes
it to fail loudly in CI.
