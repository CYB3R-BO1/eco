# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**This repository is pre-implementation.** Only two documents exist:

- `BLUEPRINT.md` — full long-term vision (7-layer AI-native security platform). Aspirational scope.
- `PLAN.md` — the **authoritative** MVP execution plan. When BLUEPRINT and PLAN conflict, PLAN wins.

There is no source code, no `pyproject.toml`, no Docker setup yet. Phase 1 (Foundation) has not begun. Do not invent build/test/lint commands — none exist. When the user asks you to start building, Phase 1 of `PLAN.md` §11 is the starting point.

## What the MVP is (and is not)

The MVP delivers exactly two flagship capabilities — do not scope-creep beyond them:

1. **AI-for-Security**: AI-powered IOC correlation & investigation engine (ingest → extract → enrich → correlate in graph → AI reasoning over evidence).
2. **Security-for-AI**: model-agnostic AI Firewall (prompt injection + jailbreak detection, risk scoring, explainable block/sanitize decisions).

Explicit non-goals (see `PLAN.md` §1): full SIEM, endpoint agents, CSPM, malware sandboxing, autonomous remediation, multi-tenant SaaS, microservices, frontend dashboards, streaming telemetry at scale. The MVP is **backend-first** and a **modular monolith** — do not split into microservices.

## Planned stack

Python + FastAPI, LangGraph for agent orchestration, Neo4j (graph), PostgreSQL (relational + evidence + events), Redis (cache + queues), OpenAI-compatible LLM APIs, Docker.

Planned top-level layout (see `PLAN.md` §4 for full tree): `apps/`, `core/`, `agents/`, `orchestration/`, `firewall/`, `investigation/`, `graph/`, `evidence/`, `resolution/`, `schemas/`, `storage/`, `tests/`, `infra/`.

## Non-negotiable architectural invariants

These are load-bearing constraints from `PLAN.md`. Violating them silently corrupts investigations or the graph — they are not stylistic preferences.

### 1. Canonical event model (`PLAN.md` §2)
Every workflow event conforms to a fixed schema (`event_id`, `event_type`, `timestamp`, `source`, `investigation_id`, `correlation_id`, `actor`, `target`, `evidence_refs`, `metadata`, `confidence`). Events are **immutable** and stored in PostgreSQL `investigation_events`. Events become graph edges, audit records, and reasoning references — there is no separate audit log path.

### 2. Graph Service is the only writer to Neo4j (`PLAN.md` §3)
**No module may write arbitrary relationships into Neo4j directly.** All mutations go through a centralized Graph Service that enforces schema validation, entity deduplication, the Relationship Matrix (allowed node-pair → relationship-type combinations in §6), evidence linkage, and timestamp consistency. Bypassing this destroys graph quality.

### 3. Entity Resolution before graph writes (`PLAN.md` §3)
`google.com`, `Google.com`, and `https://google.com/login` must resolve to canonical forms with tracked variants. Graph mutations pass through Entity Resolution → Graph Service. Skipping resolution causes duplicate-entity explosion.

### 4. Evidence Engine: reference, don't embed (`PLAN.md` §3)
All investigations, enrichments, findings, and AI outputs reference `evidence_id` — **never raw data**. Each evidence record carries a provenance level (PRIMARY_SOURCE > DERIVED_SOURCE > AI_GENERATED > THIRD_PARTY > USER_SUPPLIED) used for trust scoring. Chain-of-custody is a list of event IDs.

### 5. Deterministic and AI layers stay separate (`PLAN.md` §6)
Deterministic (regex extraction, graph relationship creation, enrichment normalization, rules, timeline, entity resolution) is reproducible and authoritative. AI (summarization, narrative, prioritization, explanation) is **assistive only**, must cite `evidence_id`s, includes confidence + provenance level, and is stored **separately** from deterministic findings. Do not let AI output overwrite or fabricate deterministic state.

### 6. Confidence is propagated, never assumed (`PLAN.md` §6)
Derived relationships inherit `min(source_reliability, enrichment_reliability, ai_confidence, corroboration_factor)`. Every graph relationship stores `confidence`. Low-confidence findings transition the investigation to `REVIEW_REQUIRED` rather than auto-completing.

### 7. Investigation lifecycle is an explicit state machine (`PLAN.md` §6)
`CREATED → ENRICHING → CORRELATING → ANALYZING → REVIEW_REQUIRED → COMPLETED → ARCHIVED` (with `FAILED` reachable from any state). Each transition emits an event and updates `investigations.status`.

### 8. Idempotency on retries (`PLAN.md` §11.6)
Events, enrichment jobs, and graph mutations all carry fingerprints/idempotency keys. Retries must not create duplicates. Graph operations upsert on `(node_id, relationship_type, target_id)`. Replays set `is_replay=true` and do not trigger downstream side effects.

### 9. Bounded memory and operational limits (`PLAN.md` §3, §3.5)
Agent memory is **investigation-scoped** with TTL, depth cap (FIFO eviction), and relevance threshold. Hard limits exist for investigation duration, event/evidence/node counts, agent concurrency, AI tokens, API rate, and graph traversal depth. Violations terminate the workflow and set state to `FAILED` — they do not silently truncate.

### 10. Failure handling is explicit, not optimistic (`PLAN.md` §10.5)
Retry policies with exponential/linear backoff, per-queue DLQs (`enrichment_dlq`, `graph_dlq`, `reasoning_dlq`, `workflow_dlq`), circuit breakers for external services. Graph is **append-only — no automatic rollback**. On AI provider failure, continue with deterministic findings and mark investigation `AI_UNAVAILABLE`; do not silently degrade to a local LLM.

### 11. RBAC checks every `(role, resource, action)` (`PLAN.md` §11.7)
Roles: `admin`, `analyst`, `readonly`, `external_user`, `ai_agent`, `service_account`. Deny by default on authorization-check failure. Audit-log all denials.

### 12. Privacy by default (`PLAN.md` §14.5)
Hash prompts for logs — **do not log full prompt content**. PII masking applied at output layers (logs, API responses, summaries), **not** to stored raw data. Retention varies by provenance level (PRIMARY_SOURCE 180d → AI_GENERATED 30d). Sensitive data (flagged prompts, leaked API keys) is deleted immediately with no override.

## When the user asks to start building

1. Start at `PLAN.md` Phase 1 (Foundation): repo scaffolding, Docker compose, FastAPI skeleton, PostgreSQL/Neo4j/Redis connectivity.
2. Use the structure in `PLAN.md` §4 — do not invent a different layout.
3. Resist the urge to architect further. `PLAN.md` ends with an explicit "stop architecting, start building" directive — additional design docs are out of scope unless the user requests them.
4. The schemas in `PLAN.md` §5 (PostgreSQL tables, Neo4j node/relationship types) are the source of truth for initial migrations.

## Forbidden shortcuts

- direct Neo4j writes outside Graph Service
- storing raw prompts in logs
- bypassing Entity Resolution
- AI-generated graph relationships without validation
- mutable investigation events
- synchronous enrichment execution
- hardcoded secrets or API keys